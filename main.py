import os, asyncio, json, discord, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from discord import app_commands
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque

load_dotenv()
TOKEN = os.getenv("TOKEN")

# --- IDs ---
STAFF_ROLE_ID        = 1486086431066816582
CANAL_AUTO_LOGS      = 1486088127389892609
CANAL_STAFF_LOGS     = 1486451822456737822
CANAL_COMANDOS       = 1486087293012938976
CANAL_CALIFICACIONES = 1486087968090230875
CANAL_BIENVENIDA     = 1486070953187348541
CANALES_RECOMENDADOS = [1316844873680424971, 1486072018230317186, 1486088510879432730, 1486072363513807039]

COLORES = {
    "warn": discord.Color.from_str("#F5A623"), "ban":  discord.Color.from_str("#D0021B"),
    "kick": discord.Color.from_str("#E85D04"), "mute": discord.Color.from_str("#7B2D8B"),
    "unmute": discord.Color.from_str("#27AE60"), "clear": discord.Color.from_str("#2980B9"),
    "lock": discord.Color.from_str("#C0392B"),  "unlock": discord.Color.from_str("#27AE60"),
    "info": discord.Color.from_str("#3498DB"),  "auto": discord.Color.from_str("#E74C3C"),
    "ok":   discord.Color.from_str("#2ECC71"),
}

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot  = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# --- Utilidades generales ---
def es_staff(m): return any(r.id == STAFF_ROLE_ID for r in m.roles)
def ts(): return datetime.now().strftime("%d/%m/%Y %H:%M")

def jload(path, default=None):
    if default is None: default = {}
    if not os.path.exists(path): return default
    with open(path) as f: return json.load(f)

def jsave(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=2, ensure_ascii=False)

def cargar():        return jload("sanciones.json")
def guardar(d):      jsave("sanciones.json", d)
def cargar_notas():  return jload("notas.json")
def guardar_notas(d):jsave("notas.json", d)
def cargar_cal():    return jload("calificaciones.json")
def guardar_cal(d):  jsave("calificaciones.json", d)
def cargar_tickets():return jload("tickets.json", {"counter": 0, "tickets": {}})
def guardar_tickets(d): jsave("tickets.json", d)

def gen_id(data):
    return f"#{sum(len(v) for v in data.values()) + 1:04d}"

def registrar(uid, tipo, motivo, staff):
    data = cargar(); uid = str(uid); data.setdefault(uid, [])
    sid = gen_id(data)
    data[uid].append({"id": sid, "tipo": tipo, "motivo": motivo, "staff": str(staff), "fecha": ts()})
    guardar(data); return sid

async def no_staff(i): await i.response.send_message("❌ No tienes permisos de staff.", ephemeral=True)
async def log_ch(guild, cid, embed):
    c = guild.get_channel(cid)
    if c: await c.send(embed=embed)

async def log_staff(guild, embed): await log_ch(guild, CANAL_STAFF_LOGS, embed)
async def log_auto(guild, embed):  await log_ch(guild, CANAL_AUTO_LOGS, embed)

def embed_log(tipo, staff, usuario, motivo, sid, extra=None):
    iconos = {"WARN":"⚠️","BAN":"🔨","KICK":"👢","MUTE":"🔇","UNMUTE":"🔊"}
    e = discord.Embed(title=f"{iconos.get(tipo,'📋')} {tipo} — Moderación",
                      color=COLORES.get(tipo.lower(), discord.Color.blurple()), timestamp=datetime.now(timezone.utc))
    e.set_author(name=str(staff), icon_url=staff.display_avatar.url)
    e.set_thumbnail(url=usuario.display_avatar.url)
    e.add_field(name="👤 Usuario", value=f"{usuario.mention}\n`{usuario}` — `{usuario.id}`", inline=True)
    e.add_field(name="👮 Staff",   value=f"{staff.mention}\n`{staff}`", inline=True)
    e.add_field(name="🆔 ID",      value=f"`{sid}`", inline=True)
    e.add_field(name="📝 Motivo",  value=motivo, inline=False)
    if extra: e.add_field(name="📌 Extra", value=extra, inline=False)
    e.set_footer(text=f"Fecha: {ts()}"); return e

async def enviar_dm(user, guild, tipo, motivo, sid, staff, duracion=None):
    iconos = {"WARN":"⚠️","BAN":"🔨","KICK":"👢","MUTE":"🔇","AUTO-FLOOD":"🤖","AUTO-SPAM":"🤖"}
    descs  = {
        "WARN":"Has recibido una **advertencia** en el servidor.",
        "BAN":"Has sido **baneado permanentemente** del servidor.",
        "KICK":"Has sido **expulsado** del servidor.",
        "MUTE":f"Has sido **silenciado**{f' por **{duracion}**' if duracion else ''} en el servidor.",
        "AUTO-FLOOD":"El sistema automático detectó **flood** en tus mensajes.",
        "AUTO-SPAM":"El sistema detectó un **link no permitido** en tus mensajes.",
    }
    sn = staff.display_name if hasattr(staff,"display_name") else str(staff)
    st = str(staff) if hasattr(staff,"name") else "Sistema Automático"
    e = discord.Embed(title=f"{iconos.get(tipo,'🚫')} Sanción — {tipo}",
                      description=f"{descs.get(tipo,'Recibiste una sanción.')}\n\nContactá un administrador si fue un error.",
                      color=COLORES.get(tipo.lower().replace("auto-","auto"), COLORES["auto"]), timestamp=datetime.now(timezone.utc))
    e.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
    if hasattr(staff,"display_avatar"): e.set_thumbnail(url=staff.display_avatar.url)
    e.add_field(name="🏠 Servidor", value=guild.name, inline=True)
    e.add_field(name="📋 Tipo",     value=tipo,       inline=True)
    e.add_field(name="🆔 ID",       value=f"`{sid}`", inline=True)
    e.add_field(name="📝 Motivo",   value=motivo,     inline=False)
    e.add_field(name="👮 Staff",    value=f"{sn} (`{st}`)", inline=True)
    e.add_field(name="📅 Fecha",    value=ts(),       inline=True)
    if duracion: e.add_field(name="⏳ Duración", value=duracion, inline=True)
    e.set_footer(text="No respondas — mensaje automático.")
    try: await user.send(embed=e)
    except: pass

# --- Auto-mod ---
user_msgs = defaultdict(lambda: deque(maxlen=5))

def automod_embed(titulo, autor, sid, canal):
    e = discord.Embed(title=titulo, color=COLORES["auto"], timestamp=datetime.now(timezone.utc))
    e.set_thumbnail(url=autor.display_avatar.url)
    e.add_field(name="👤 Usuario", value=f"{autor.mention} (`{autor}`)", inline=True)
    e.add_field(name="🆔 ID",      value=f"`{sid}`",                     inline=True)
    e.add_field(name="📋 Canal",   value=canal.mention,                  inline=True)
    e.set_footer(text=ts()); return e

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot: return
    if message.content.strip().lower() == "!panel-send":
        try: await message.delete()
        except: pass
        if es_staff(message.author): await enviar_panel_tickets(message.channel, message.guild)
        return
    if isinstance(message.author, discord.Member) and es_staff(message.author): return
    now = datetime.now().timestamp()
    user_msgs[message.author.id].append(now)
    if len(user_msgs[message.author.id]) >= 5 and now - user_msgs[message.author.id][0] <= 5:
        try: await message.delete()
        except: pass
        sid = registrar(message.author.id, "AUTO-FLOOD", "Flood detectado", "Sistema")
        await enviar_dm(message.author, message.guild, "AUTO-FLOOD", "Enviaste demasiados mensajes en poco tiempo.", sid, "Sistema Automático")
        await log_auto(message.guild, automod_embed("🤖 Flood detectado", message.author, sid, message.channel)); return
    if "http://" in message.content or "https://" in message.content:
        try: await message.delete()
        except: pass
        sid = registrar(message.author.id, "AUTO-SPAM", "Link no permitido", "Sistema")
        await enviar_dm(message.author, message.guild, "AUTO-SPAM", "No se permiten links en este servidor.", sid, "Sistema Automático")
        await log_auto(message.guild, automod_embed("🤖 Link detectado", message.author, sid, message.channel))

# --- Comandos de moderación ---
@tree.command(name="warn", description="Advertir a un usuario")
@app_commands.describe(usuario="Usuario", motivo="Motivo")
async def warn(i: discord.Interaction, usuario: discord.Member, motivo: str):
    if not es_staff(i.user): return await no_staff(i)
    sid = registrar(usuario.id, "WARN", motivo, i.user.id)
    await enviar_dm(usuario, i.guild, "WARN", motivo, sid, i.user)
    e = embed_log("WARN", i.user, usuario, motivo, sid)
    await i.response.send_message(embed=e); await log_staff(i.guild, e)

@tree.command(name="ban", description="Banear a un usuario")
@app_commands.describe(usuario="Usuario", motivo="Motivo")
async def ban(i: discord.Interaction, usuario: discord.Member, motivo: str = "Sin motivo"):
    if not es_staff(i.user): return await no_staff(i)
    sid = registrar(usuario.id, "BAN", motivo, i.user.id)
    await enviar_dm(usuario, i.guild, "BAN", motivo, sid, i.user)
    e = embed_log("BAN", i.user, usuario, motivo, sid)
    try: await usuario.ban(reason=f"[{sid}] {motivo}")
    except discord.Forbidden: return await i.response.send_message("❌ Sin permisos para banear.", ephemeral=True)
    await i.response.send_message(embed=e); await log_staff(i.guild, e)

@tree.command(name="kick", description="Expulsar a un usuario")
@app_commands.describe(usuario="Usuario", motivo="Motivo")
async def kick(i: discord.Interaction, usuario: discord.Member, motivo: str = "Sin motivo"):
    if not es_staff(i.user): return await no_staff(i)
    sid = registrar(usuario.id, "KICK", motivo, i.user.id)
    await enviar_dm(usuario, i.guild, "KICK", motivo, sid, i.user)
    e = embed_log("KICK", i.user, usuario, motivo, sid)
    try: await usuario.kick(reason=f"[{sid}] {motivo}")
    except discord.Forbidden: return await i.response.send_message("❌ Sin permisos para expulsar.", ephemeral=True)
    await i.response.send_message(embed=e); await log_staff(i.guild, e)

@tree.command(name="mute", description="Silenciar a un usuario")
@app_commands.describe(usuario="Usuario", minutos="Duración en minutos", motivo="Motivo")
async def mute(i: discord.Interaction, usuario: discord.Member, minutos: int, motivo: str = "Sin motivo"):
    if not es_staff(i.user): return await no_staff(i)
    if not 1 <= minutos <= 40320: return await i.response.send_message("❌ Entre 1 y 40320 minutos.", ephemeral=True)
    dur = f"{minutos} minuto{'s' if minutos != 1 else ''}"
    sid = registrar(usuario.id, "MUTE", motivo, i.user.id)
    await enviar_dm(usuario, i.guild, "MUTE", motivo, sid, i.user, duracion=dur)
    try: await usuario.timeout(discord.utils.utcnow() + timedelta(minutes=minutos), reason=f"[{sid}] {motivo}")
    except discord.Forbidden: return await i.response.send_message("❌ Sin permisos para mutear.", ephemeral=True)
    e = embed_log("MUTE", i.user, usuario, motivo, sid, extra=f"⏳ Duración: **{dur}**")
    await i.response.send_message(embed=e); await log_staff(i.guild, e)

@tree.command(name="unmute", description="Quitar silencio a un usuario")
@app_commands.describe(usuario="Usuario")
async def unmute(i: discord.Interaction, usuario: discord.Member):
    if not es_staff(i.user): return await no_staff(i)
    try: await usuario.timeout(None)
    except discord.Forbidden: return await i.response.send_message("❌ Sin permisos para desmutear.", ephemeral=True)
    e = discord.Embed(title="🔊 UNMUTE", color=COLORES["unmute"], timestamp=datetime.now(timezone.utc))
    e.set_author(name=str(i.user), icon_url=i.user.display_avatar.url)
    e.set_thumbnail(url=usuario.display_avatar.url)
    e.add_field(name="👤 Usuario", value=f"{usuario.mention} (`{usuario}`)", inline=True)
    e.add_field(name="👮 Staff",   value=i.user.mention, inline=True)
    e.set_footer(text=ts())
    await i.response.send_message(embed=e); await log_staff(i.guild, e)

@tree.command(name="clear", description="Eliminar mensajes del canal")
@app_commands.describe(cantidad="Cantidad (1–100)")
async def clear(i: discord.Interaction, cantidad: int):
    if not es_staff(i.user): return await no_staff(i)
    if not 1 <= cantidad <= 100: return await i.response.send_message("❌ Entre 1 y 100.", ephemeral=True)
    await i.response.defer(ephemeral=True)
    deleted = await i.channel.purge(limit=cantidad)
    e = discord.Embed(title="🧹 CLEAR", color=COLORES["clear"], timestamp=datetime.now(timezone.utc))
    e.set_author(name=str(i.user), icon_url=i.user.display_avatar.url)
    e.add_field(name="🗑️ Eliminados", value=f"**{len(deleted)}** mensajes", inline=True)
    e.add_field(name="📋 Canal",      value=i.channel.mention,              inline=True)
    e.add_field(name="👮 Staff",      value=i.user.mention,                 inline=True)
    e.set_footer(text=ts())
    await i.followup.send(embed=e, ephemeral=True); await log_staff(i.guild, e)

@tree.command(name="lock", description="Bloquear canal")
@app_commands.describe(motivo="Motivo")
async def lock(i: discord.Interaction, motivo: str = "Sin motivo"):
    if not es_staff(i.user): return await no_staff(i)
    try: await i.channel.set_permissions(i.guild.default_role, send_messages=False)
    except discord.Forbidden: return await i.response.send_message("❌ Sin permisos.", ephemeral=True)
    e = discord.Embed(title="🔒 LOCK — Canal bloqueado", description=f"Bloqueado por {i.user.mention}.",
                      color=COLORES["lock"], timestamp=datetime.now(timezone.utc))
    e.add_field(name="📝 Motivo", value=motivo); e.set_footer(text=f"Staff: {i.user} • {ts()}")
    await i.response.send_message(embed=e); await log_staff(i.guild, e)

@tree.command(name="unlock", description="Desbloquear canal")
async def unlock(i: discord.Interaction):
    if not es_staff(i.user): return await no_staff(i)
    try: await i.channel.set_permissions(i.guild.default_role, send_messages=True)
    except discord.Forbidden: return await i.response.send_message("❌ Sin permisos.", ephemeral=True)
    e = discord.Embed(title="🔓 UNLOCK — Canal desbloqueado", description=f"Desbloqueado por {i.user.mention}.",
                      color=COLORES["unlock"], timestamp=datetime.now(timezone.utc))
    e.set_footer(text=f"Staff: {i.user} • {ts()}")
    await i.response.send_message(embed=e); await log_staff(i.guild, e)

@tree.command(name="slowmode", description="Modo lento en el canal")
@app_commands.describe(segundos="Segundos (0 = desactivar)")
async def slowmode(i: discord.Interaction, segundos: int):
    if not es_staff(i.user): return await no_staff(i)
    if not 0 <= segundos <= 21600: return await i.response.send_message("❌ Entre 0 y 21600 seg.", ephemeral=True)
    try: await i.channel.edit(slowmode_delay=segundos)
    except discord.Forbidden: return await i.response.send_message("❌ Sin permisos.", ephemeral=True)
    activo = segundos > 0
    e = discord.Embed(title=f"{'🐢 SLOWMODE activado' if activo else '⚡ SLOWMODE desactivado'}",
                      description=f"**{segundos}s** entre mensajes." if activo else "Modo lento desactivado.",
                      color=COLORES["mute"] if activo else COLORES["ok"], timestamp=datetime.now(timezone.utc))
    e.add_field(name="👮 Staff", value=i.user.mention, inline=True)
    e.add_field(name="📋 Canal", value=i.channel.mention, inline=True)
    e.set_footer(text=ts())
    await i.response.send_message(embed=e); await log_staff(i.guild, e)

# --- Warnings ---
class BorrarSancionSelect(discord.ui.Select):
    def __init__(self, usuario, sanciones):
        super().__init__(placeholder="Seleccioná una sanción para eliminar...", options=[
            discord.SelectOption(label=f"{s['id']} — {s['tipo']}", description=s["motivo"][:100], value=s["id"])
            for s in sanciones
        ])
        self.usuario = usuario
    async def callback(self, i: discord.Interaction):
        if not es_staff(i.user): return await i.response.send_message("❌ Sin permisos.", ephemeral=True)
        data = cargar(); uid = str(self.usuario.id)
        antes = len(data.get(uid, []))
        data[uid] = [s for s in data.get(uid, []) if s["id"] != self.values[0]]
        guardar(data)
        msg = f"✅ Sanción `{self.values[0]}` eliminada." if len(data[uid]) < antes else f"❌ No encontrada."
        await i.response.send_message(msg, ephemeral=True)

class VistaWarnings(discord.ui.View):
    def __init__(self, usuario, sanciones):
        super().__init__(timeout=120); self.add_item(BorrarSancionSelect(usuario, sanciones))

@tree.command(name="warnings", description="Historial de sanciones de un usuario")
@app_commands.describe(usuario="Usuario")
async def warnings(i: discord.Interaction, usuario: discord.Member):
    if not es_staff(i.user): return await no_staff(i)
    data = cargar(); uid = str(usuario.id); sanciones = data.get(uid, [])
    if not sanciones:
        e = discord.Embed(title="📋 Historial limpio", description=f"{usuario.mention} no tiene sanciones.", color=COLORES["ok"])
        e.set_thumbnail(url=usuario.display_avatar.url)
        return await i.response.send_message(embed=e, ephemeral=True)
    iconos = {"WARN":"⚠️","BAN":"🔨","KICK":"👢","MUTE":"🔇","AUTO-FLOOD":"🤖","AUTO-SPAM":"🤖"}
    e = discord.Embed(title=f"📋 Sanciones — {usuario.display_name}", description=f"Total: **{len(sanciones)}**",
                      color=COLORES["info"], timestamp=datetime.now(timezone.utc))
    e.set_thumbnail(url=usuario.display_avatar.url)
    e.set_author(name=str(usuario), icon_url=usuario.display_avatar.url)
    for s in sanciones[-10:]:
        e.add_field(name=f"{iconos.get(s['tipo'],'📋')} {s['id']} — {s['tipo']}",
                    value=f"**Motivo:** {s['motivo']}\n**Staff:** {s['staff']}\n**Fecha:** {s['fecha']}", inline=False)
    e.set_footer(text=f"Últimas 10 de {len(sanciones)}" if len(sanciones)>10 else f"Solicitado por {i.user}")
    await i.response.send_message(embed=e, view=VistaWarnings(usuario, sanciones), ephemeral=True)

# --- Userinfo ---
@tree.command(name="userinfo", description="Información de un usuario")
@app_commands.describe(usuario="Usuario (opcional)")
async def userinfo(i: discord.Interaction, usuario: discord.Member = None):
    if not es_staff(i.user): return await no_staff(i)
    t = usuario or i.user
    sanciones = len(cargar().get(str(t.id), []))
    roles = " ".join(r.mention for r in reversed(t.roles) if r.id != i.guild.id) or "Sin roles"
    e = discord.Embed(title=f"👤 {t.display_name}", color=COLORES["info"], timestamp=datetime.now(timezone.utc))
    e.set_thumbnail(url=t.display_avatar.url)
    e.add_field(name="🏷️ Tag",          value=str(t),                                                       inline=True)
    e.add_field(name="🆔 ID",           value=f"`{t.id}`",                                                  inline=True)
    e.add_field(name="🤖 Bot",          value="Sí" if t.bot else "No",                                     inline=True)
    e.add_field(name="📅 Cuenta creada",value=t.created_at.strftime("%d/%m/%Y"),                           inline=True)
    e.add_field(name="📅 Se unió",      value=t.joined_at.strftime("%d/%m/%Y") if t.joined_at else "?",    inline=True)
    e.add_field(name="⚠️ Sanciones",    value=f"**{sanciones}** registradas",                              inline=True)
    e.add_field(name="🎭 Roles",        value=roles[:1024],                                                 inline=False)
    e.set_footer(text=f"Solicitado por {i.user}")
    await i.response.send_message(embed=e, ephemeral=True)

# --- Moderación avanzada ---
@tree.command(name="unban", description="Desbanear por ID")
@app_commands.describe(usuario_id="ID del usuario", motivo="Motivo")
async def unban(i: discord.Interaction, usuario_id: str, motivo: str = "Sin motivo"):
    if not es_staff(i.user): return await no_staff(i)
    try: uid = int(usuario_id)
    except: return await i.response.send_message("❌ ID inválido.", ephemeral=True)
    try:
        user = await bot.fetch_user(uid)
        await i.guild.unban(user, reason=f"{motivo} — por {i.user}")
    except discord.NotFound: return await i.response.send_message("❌ Sin ban registrado para ese ID.", ephemeral=True)
    except discord.Forbidden: return await i.response.send_message("❌ Sin permisos.", ephemeral=True)
    e = discord.Embed(title="✅ UNBAN", color=COLORES["ok"], timestamp=datetime.now(timezone.utc))
    e.set_author(name=str(i.user), icon_url=i.user.display_avatar.url)
    e.set_thumbnail(url=user.display_avatar.url)
    e.add_field(name="👤 Usuario", value=f"`{user}` — `{user.id}`", inline=True)
    e.add_field(name="👮 Staff",   value=i.user.mention,            inline=True)
    e.add_field(name="📝 Motivo",  value=motivo,                    inline=False)
    e.set_footer(text=ts())
    await i.response.send_message(embed=e); await log_staff(i.guild, e)

@tree.command(name="nick", description="Cambiar apodo de un usuario")
@app_commands.describe(usuario="Usuario", nombre="Nuevo apodo (vacío = resetear)")
async def nick(i: discord.Interaction, usuario: discord.Member, nombre: str = None):
    if not es_staff(i.user): return await no_staff(i)
    anterior = usuario.display_name
    try: await usuario.edit(nick=nombre)
    except discord.Forbidden: return await i.response.send_message("❌ Sin permisos.", ephemeral=True)
    e = discord.Embed(title="✏️ NICK", color=COLORES["info"], timestamp=datetime.now(timezone.utc))
    e.set_thumbnail(url=usuario.display_avatar.url)
    e.add_field(name="👤 Usuario", value=f"{usuario.mention}", inline=False)
    e.add_field(name="📛 Antes",   value=anterior,             inline=True)
    e.add_field(name="✅ Ahora",    value=nombre or usuario.name, inline=True)
    e.add_field(name="👮 Staff",   value=i.user.mention,       inline=True)
    e.set_footer(text=ts())
    await i.response.send_message(embed=e, ephemeral=True); await log_staff(i.guild, e)

@tree.command(name="rol-add", description="Añadir rol a un usuario")
@app_commands.describe(usuario="Usuario", rol="Rol")
async def rol_add(i: discord.Interaction, usuario: discord.Member, rol: discord.Role):
    if not es_staff(i.user): return await no_staff(i)
    if rol in usuario.roles: return await i.response.send_message(f"❌ Ya tiene {rol.mention}.", ephemeral=True)
    try: await usuario.add_roles(rol)
    except discord.Forbidden: return await i.response.send_message("❌ Sin permisos.", ephemeral=True)
    e = discord.Embed(title="➕ ROL AÑADIDO", color=rol.color if rol.color.value else COLORES["ok"], timestamp=datetime.now(timezone.utc))
    e.set_thumbnail(url=usuario.display_avatar.url)
    e.add_field(name="👤 Usuario", value=f"{usuario.mention}", inline=True)
    e.add_field(name="🎭 Rol",     value=rol.mention,          inline=True)
    e.add_field(name="👮 Staff",   value=i.user.mention,       inline=True)
    e.set_footer(text=ts())
    await i.response.send_message(embed=e, ephemeral=True); await log_staff(i.guild, e)

@tree.command(name="rol-remove", description="Quitar rol a un usuario")
@app_commands.describe(usuario="Usuario", rol="Rol")
async def rol_remove(i: discord.Interaction, usuario: discord.Member, rol: discord.Role):
    if not es_staff(i.user): return await no_staff(i)
    if rol not in usuario.roles: return await i.response.send_message(f"❌ No tiene {rol.mention}.", ephemeral=True)
    try: await usuario.remove_roles(rol)
    except discord.Forbidden: return await i.response.send_message("❌ Sin permisos.", ephemeral=True)
    e = discord.Embed(title="➖ ROL QUITADO", color=COLORES["warn"], timestamp=datetime.now(timezone.utc))
    e.set_thumbnail(url=usuario.display_avatar.url)
    e.add_field(name="👤 Usuario", value=f"{usuario.mention}", inline=True)
    e.add_field(name="🎭 Rol",     value=rol.mention,          inline=True)
    e.add_field(name="👮 Staff",   value=i.user.mention,       inline=True)
    e.set_footer(text=ts())
    await i.response.send_message(embed=e, ephemeral=True); await log_staff(i.guild, e)

@tree.command(name="bans", description="Lista de usuarios baneados")
async def bans(i: discord.Interaction):
    if not es_staff(i.user): return await no_staff(i)
    await i.response.defer(ephemeral=True)
    try: ban_list = [entry async for entry in i.guild.bans()]
    except discord.Forbidden: return await i.followup.send("❌ Sin permisos.", ephemeral=True)
    if not ban_list: return await i.followup.send("✅ No hay baneados.", ephemeral=True)
    e = discord.Embed(title=f"🔨 Baneados — {len(ban_list)}", color=COLORES["ban"], timestamp=datetime.now(timezone.utc))
    e.description = "\n".join(f"• **{x.user}** (`{x.user.id}`) — {(x.reason or 'Sin motivo')[:60]}" for x in ban_list[:25])
    if len(ban_list) > 25: e.set_footer(text=f"Mostrando 25 de {len(ban_list)}")
    await i.followup.send(embed=e, ephemeral=True)

# --- Serverinfo ---
@tree.command(name="serverinfo", description="Información del servidor")
async def serverinfo(i: discord.Interaction):
    if not es_staff(i.user): return await no_staff(i)
    g = i.guild
    bots = sum(1 for m in g.members if m.bot)
    e = discord.Embed(title=f"🏠 {g.name}", description=g.description or "Sin descripción.",
                      color=COLORES["info"], timestamp=datetime.now(timezone.utc))
    if g.icon: e.set_thumbnail(url=g.icon.url)
    if g.banner: e.set_image(url=g.banner.url)
    e.add_field(name="🆔 ID",          value=f"`{g.id}`",                                            inline=True)
    e.add_field(name="👑 Dueño",       value=g.owner.mention if g.owner else "?",                    inline=True)
    e.add_field(name="📅 Creado",      value=g.created_at.strftime("%d/%m/%Y"),                      inline=True)
    e.add_field(name="👥 Miembros",    value=f"**{g.member_count-bots}** humanos • **{bots}** bots", inline=True)
    e.add_field(name="💬 Canales",     value=f"**{len(g.text_channels)}** texto • **{len(g.voice_channels)}** voz", inline=True)
    e.add_field(name="🎭 Roles",       value=f"**{len(g.roles)}**",                                  inline=True)
    e.add_field(name="🚀 Boost",       value=f"Nivel **{g.premium_tier}** — **{g.premium_subscription_count}** boosts", inline=True)
    e.add_field(name="😀 Emojis",      value=f"**{len(g.emojis)}**",                                 inline=True)
    e.add_field(name="🔒 Verificación",value=str(g.verification_level).capitalize(),                 inline=True)
    e.set_footer(text=f"Solicitado por {i.user}")
    await i.response.send_message(embed=e, ephemeral=True)

# --- Notas internas ---
@tree.command(name="nota", description="Añadir nota interna sobre un usuario")
@app_commands.describe(usuario="Usuario", texto="Nota")
async def nota(i: discord.Interaction, usuario: discord.Member, texto: str):
    if not es_staff(i.user): return await no_staff(i)
    notas = cargar_notas(); uid = str(usuario.id); notas.setdefault(uid, [])
    notas[uid].append({"texto": texto, "staff": str(i.user), "fecha": ts()})
    guardar_notas(notas)
    e = discord.Embed(title="📝 Nota añadida", color=COLORES["info"], timestamp=datetime.now(timezone.utc))
    e.set_thumbnail(url=usuario.display_avatar.url)
    e.add_field(name="👤 Usuario", value=f"{usuario.mention}", inline=True)
    e.add_field(name="👮 Staff",   value=i.user.mention,       inline=True)
    e.add_field(name="📝 Nota",    value=texto,                inline=False)
    e.set_footer(text=f"Total notas: {len(notas[uid])}")
    await i.response.send_message(embed=e, ephemeral=True)

@tree.command(name="notas", description="Ver notas internas de un usuario")
@app_commands.describe(usuario="Usuario")
async def notas_cmd(i: discord.Interaction, usuario: discord.Member):
    if not es_staff(i.user): return await no_staff(i)
    lista = cargar_notas().get(str(usuario.id), [])
    if not lista: return await i.response.send_message(f"📝 {usuario.mention} no tiene notas.", ephemeral=True)
    e = discord.Embed(title=f"📝 Notas — {usuario.display_name}", description=f"Total: **{len(lista)}**",
                      color=COLORES["info"], timestamp=datetime.now(timezone.utc))
    e.set_thumbnail(url=usuario.display_avatar.url)
    for idx, n in enumerate(lista[-10:], 1):
        e.add_field(name=f"📌 Nota #{idx}", value=f"{n['texto']}\n— *{n['staff']}* • {n['fecha']}", inline=False)
    e.set_footer(text=f"Solicitado por {i.user}")
    await i.response.send_message(embed=e, ephemeral=True)

# --- Reportes ---
class ReporteView(discord.ui.View):
    def __init__(self, reportado, reportador, motivo):
        super().__init__(timeout=None)
        self.reportado = reportado; self.reportador = reportador; self.motivo = motivo

    def _disable(self):
        for item in self.children: item.disabled = True

    @discord.ui.button(label="⚠️ Warn", style=discord.ButtonStyle.danger)
    async def btn_warn(self, i, b):
        if not es_staff(i.user): return await i.response.send_message("❌ Sin permisos.", ephemeral=True)
        sid = registrar(self.reportado.id, "WARN", f"Reporte: {self.motivo}", i.user.id)
        await enviar_dm(self.reportado, i.guild, "WARN", f"Reporte: {self.motivo}", sid, i.user)
        e = embed_log("WARN", i.user, self.reportado, f"Reporte: {self.motivo}", sid)
        await i.response.send_message(embed=e, ephemeral=True); await log_staff(i.guild, e)
        self._disable(); await i.message.edit(view=self)

    @discord.ui.button(label="🔇 Mute 10min", style=discord.ButtonStyle.secondary)
    async def btn_mute(self, i, b):
        if not es_staff(i.user): return await i.response.send_message("❌ Sin permisos.", ephemeral=True)
        try:
            sid = registrar(self.reportado.id, "MUTE", f"Reporte: {self.motivo}", i.user.id)
            await self.reportado.timeout(discord.utils.utcnow() + timedelta(minutes=10))
            await enviar_dm(self.reportado, i.guild, "MUTE", f"Reporte: {self.motivo}", sid, i.user, "10 minutos")
            e = embed_log("MUTE", i.user, self.reportado, f"Reporte: {self.motivo}", sid, extra="⏳ **10 minutos**")
            await i.response.send_message(embed=e, ephemeral=True); await log_staff(i.guild, e)
        except: await i.response.send_message("❌ No se pudo mutear.", ephemeral=True)
        self._disable(); await i.message.edit(view=self)

    @discord.ui.button(label="✅ Ignorar", style=discord.ButtonStyle.success)
    async def btn_ignorar(self, i, b):
        if not es_staff(i.user): return await i.response.send_message("❌ Sin permisos.", ephemeral=True)
        await i.response.send_message("✅ Reporte ignorado.", ephemeral=True)
        self._disable(); await i.message.edit(view=self)

@tree.command(name="report", description="Reportar a un usuario al staff")
@app_commands.describe(usuario="Usuario a reportar", motivo="Motivo")
async def report(i: discord.Interaction, usuario: discord.Member, motivo: str):
    if usuario.id == i.user.id: return await i.response.send_message("❌ No podés reportarte a vos mismo.", ephemeral=True)
    if usuario.bot: return await i.response.send_message("❌ No podés reportar bots.", ephemeral=True)
    canal = i.guild.get_channel(CANAL_STAFF_LOGS)
    if not canal: return await i.response.send_message("❌ Error interno.", ephemeral=True)
    e = discord.Embed(title="🚨 Nuevo reporte", description="Un miembro reportó a otro usuario.",
                      color=discord.Color.from_str("#FF4500"), timestamp=datetime.now(timezone.utc))
    e.set_thumbnail(url=usuario.display_avatar.url)
    e.add_field(name="🎯 Reportado",  value=f"{usuario.mention}\n`{usuario}` — `{usuario.id}`", inline=True)
    e.add_field(name="📢 Reportador", value=f"{i.user.mention}\n`{i.user}`",                    inline=True)
    e.add_field(name="📝 Motivo",     value=motivo,                                              inline=False)
    e.add_field(name="📋 Canal",      value=i.channel.mention,                                   inline=True)
    e.set_footer(text="Usá los botones para actuar.")
    await canal.send(embed=e, view=ReporteView(usuario, i.user, motivo))
    await i.response.send_message("✅ Reporte enviado al staff. ¡Gracias!", ephemeral=True)

# --- Raid mode ---
raid_guilds: set = set()

@tree.command(name="raid-mode", description="Activar/desactivar modo anti-raid")
@app_commands.describe(estado="on o off")
@app_commands.choices(estado=[app_commands.Choice(name="Activar", value="on"), app_commands.Choice(name="Desactivar", value="off")])
async def raid_mode(i: discord.Interaction, estado: app_commands.Choice[str]):
    if not es_staff(i.user): return await no_staff(i)
    on = estado.value == "on"
    if on: raid_guilds.add(i.guild.id)
    else:  raid_guilds.discard(i.guild.id)
    e = discord.Embed(
        title=f"🛡️ RAID MODE — {'ACTIVADO' if on else 'DESACTIVADO'}",
        description="Cuentas nuevas serán silenciadas 30 min automáticamente." if on else "Modo anti-raid desactivado.",
        color=COLORES["ban"] if on else COLORES["ok"], timestamp=datetime.now(timezone.utc))
    e.add_field(name="👮 Staff", value=i.user.mention, inline=True)
    e.add_field(name="📅 Fecha", value=ts(),           inline=True)
    e.set_footer(text=i.guild.name)
    await i.response.send_message(embed=e); await log_staff(i.guild, e)

# --- Borrar sanciones ---
class ConfirmarBorradoView(discord.ui.View):
    def __init__(self, usuario, total):
        super().__init__(timeout=30); self.usuario = usuario; self.total = total

    def _disable(self):
        for item in self.children: item.disabled = True

    @discord.ui.button(label="✅ Sí, borrar todo", style=discord.ButtonStyle.danger)
    async def confirmar(self, i, b):
        if not es_staff(i.user): return await i.response.send_message("❌ Sin permisos.", ephemeral=True)
        data = cargar(); uid = str(self.usuario.id); data[uid] = []; guardar(data)
        e = discord.Embed(title="🗑️ Sanciones eliminadas",
                          description=f"Se eliminaron **{self.total}** sanciones de {self.usuario.mention}.",
                          color=COLORES["ok"], timestamp=datetime.now(timezone.utc))
        e.add_field(name="👮 Staff", value=i.user.mention); e.set_footer(text=ts())
        self._disable(); await i.response.edit_message(embed=e, view=self); await log_staff(i.guild, e)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, i, b):
        self._disable(); await i.response.edit_message(content="❌ Cancelado.", embed=None, view=self)

@tree.command(name="borrar-sanciones", description="Borrar TODAS las sanciones de un usuario")
@app_commands.describe(usuario="Usuario")
async def borrar_sanciones(i: discord.Interaction, usuario: discord.Member):
    if not es_staff(i.user): return await no_staff(i)
    sanciones = cargar().get(str(usuario.id), [])
    if not sanciones: return await i.response.send_message(f"✅ {usuario.mention} no tiene sanciones.", ephemeral=True)
    e = discord.Embed(title="⚠️ ¿Confirmar borrado total?",
                      description=f"Vas a eliminar **{len(sanciones)}** sanción(es) de {usuario.mention}.\n**Esta acción no se puede deshacer.**",
                      color=COLORES["warn"])
    e.set_thumbnail(url=usuario.display_avatar.url); e.set_footer(text="Expira en 30 segundos.")
    await i.response.send_message(embed=e, view=ConfirmarBorradoView(usuario, len(sanciones)), ephemeral=True)

# --- Calificaciones ---
def estrellas(p): return "⭐" * int(round(p)) + "✦" * (5 - int(round(p)))
def barra(v, mx=5.0, n=10):
    r = round((v/mx)*n) if mx else 0; return "▰"*r + "▱"*(n-r)

class CalificarModal(discord.ui.Modal, title="✦ Calificar staff"):
    puntuacion = discord.ui.TextInput(label="Puntuación (1 al 5)", placeholder="1 al 5...", min_length=1, max_length=1)
    comentario = discord.ui.TextInput(label="Comentario (opcional)", style=discord.TextStyle.paragraph, required=False, max_length=300)

    def __init__(self, staff_member):
        super().__init__(); self.staff_member = staff_member

    async def on_submit(self, i: discord.Interaction):
        try:
            score = int(self.puntuacion.value)
            if not 1 <= score <= 5: raise ValueError
        except: return await i.response.send_message("❌ Puntuación debe ser 1 a 5.", ephemeral=True)
        uid = str(self.staff_member.id); data = cargar_cal(); data.setdefault(uid, [])
        if any(str(c["calificador_id"]) == str(i.user.id) for c in data[uid]):
            return await i.response.send_message("❌ Ya calificaste a este staff.", ephemeral=True)
        comentario = self.comentario.value.strip() or "Sin comentario."
        data[uid].append({"puntuacion": score, "comentario": comentario, "calificador_id": str(i.user.id), "calificador": str(i.user), "fecha": ts()})
        guardar_cal(data)
        promedio = sum(c["puntuacion"] for c in data[uid]) / len(data[uid])
        canal = i.guild.get_channel(CANAL_CALIFICACIONES)
        if canal:
            e = discord.Embed(description="```\n  ✦ NUEVA CALIFICACIÓN DE STAFF ✦\n```",
                              color=discord.Color.from_str("#FFD700"), timestamp=datetime.now(timezone.utc))
            e.set_author(name=f"✦  {self.staff_member.display_name}  ✦", icon_url=self.staff_member.display_avatar.url)
            e.set_thumbnail(url=self.staff_member.display_avatar.url)
            e.add_field(name="╔═ 👮 Staff",        value=f"┃ {self.staff_member.mention}\n┗ `{self.staff_member}`", inline=True)
            e.add_field(name="╔═ 📢 Calificado por",value=f"┃ {i.user.mention}\n┗ `{i.user}`",                    inline=True)
            e.add_field(name="\u200b", value="\u200b", inline=False)
            e.add_field(name="╔═ ⭐ Puntuación",   value=f"┃ {estrellas(score)} **{score}/5**\n┗ {barra(score)}",  inline=True)
            e.add_field(name="╔═ 📊 Promedio",     value=f"┃ {estrellas(promedio)} **{promedio:.2f}/5**\n┗ {barra(promedio)} — {len(data[uid])} reseña{'s' if len(data[uid])!=1 else ''}", inline=True)
            e.add_field(name="\u200b", value="\u200b", inline=False)
            e.add_field(name="╔═ 💬 Comentario",   value=f"┗ *\"{comentario}\"*", inline=False)
            e.set_footer(text=f"✦ Sistema de calificaciones  •  {ts()}", icon_url=i.guild.icon.url if i.guild.icon else None)
            await canal.send(embed=e)
        conf = discord.Embed(title="✅ Calificación enviada", description=f"Gracias por calificar a **{self.staff_member.display_name}**.",
                             color=COLORES["ok"])
        conf.add_field(name="⭐ Tu puntuación", value=f"{estrellas(score)} **{score}/5**")
        conf.set_footer(text="Solo se permite una calificación por staff.")
        await i.response.send_message(embed=conf, ephemeral=True)

@tree.command(name="calificar-staff", description="Calificar a un miembro del staff")
@app_commands.describe(staff="Staff a calificar")
async def calificar_staff(i: discord.Interaction, staff: discord.Member):
    if i.channel_id != CANAL_COMANDOS:
        c = i.guild.get_channel(CANAL_COMANDOS)
        return await i.response.send_message(f"❌ Usá este comando en {c.mention if c else f'`#{CANAL_COMANDOS}`'}.", ephemeral=True)
    if not any(r.id == STAFF_ROLE_ID for r in staff.roles): return await i.response.send_message("❌ Ese usuario no es staff.", ephemeral=True)
    if staff.id == i.user.id: return await i.response.send_message("❌ No podés calificarte a vos mismo.", ephemeral=True)
    if staff.bot: return await i.response.send_message("❌ No podés calificar bots.", ephemeral=True)
    await i.response.send_modal(CalificarModal(staff))

@tree.command(name="stats-mod", description="Estadísticas de un miembro del staff")
@app_commands.describe(staff="Staff (opcional, por defecto el tuyo)")
async def stats_mod(i: discord.Interaction, staff: discord.Member = None):
    if not es_staff(i.user): return await no_staff(i)
    t = staff or i.user
    if not any(r.id == STAFF_ROLE_ID for r in t.roles): return await i.response.send_message("❌ No es staff.", ephemeral=True)
    conteo = {}
    for lst in cargar().values():
        for s in lst:
            if s.get("staff") == str(t.id): conteo[s["tipo"]] = conteo.get(s["tipo"], 0) + 1
    total = sum(conteo.values())
    cal_lista = cargar_cal().get(str(t.id), [])
    n_cal = len(cal_lista)
    promedio = sum(c["puntuacion"] for c in cal_lista) / n_cal if cal_lista else 0.0
    dist = {k: sum(1 for c in cal_lista if c["puntuacion"]==k) for k in range(1,6)}
    e = discord.Embed(description="```\n  ✦ ESTADÍSTICAS DE STAFF ✦\n```", color=discord.Color.from_str("#5865F2"), timestamp=datetime.now(timezone.utc))
    e.set_author(name=f"✦  {t.display_name}  ✦", icon_url=t.display_avatar.url)
    e.set_thumbnail(url=t.display_avatar.url)
    if n_cal:
        e.add_field(name="╔═ ⭐ Calificación promedio",
                    value=f"┃ {estrellas(promedio)} **{promedio:.2f}/5**\n┃ {barra(promedio)}\n┗ **{n_cal}** reseña{'s' if n_cal!=1 else ''}", inline=False)
        e.add_field(name="╔═ 📊 Distribución",
                    value="┗ " + "  ".join(f"**{k}★** {v}" for k,v in sorted(dist.items(),reverse=True) if v), inline=False)
    else:
        e.add_field(name="╔═ ⭐ Calificación", value="┗ Sin calificaciones aún.", inline=False)
    e.add_field(name="\u200b", value="\u200b", inline=False)
    e.add_field(name="╔═ 🛡️ Acciones de moderación",
                value=f"┃ ⚠️ Warns: **{conteo.get('WARN',0)}**\n┃ 🔨 Bans: **{conteo.get('BAN',0)}**\n"
                      f"┃ 👢 Kicks: **{conteo.get('KICK',0)}**\n┃ 🔇 Mutes: **{conteo.get('MUTE',0)}**\n"
                      f"┗ 📦 Total: **{total}**", inline=False)
    e.set_footer(text=f"✦ Solicitado por {i.user}  •  {ts()}", icon_url=i.user.display_avatar.url)
    await i.response.send_message(embed=e, ephemeral=True)

# --- Sistema de tickets ---
TIPOS_TICKET = {
    "soporte_general":     ("Soporte General",      "Member",    1486085000117092382),
    "soporte_tecnico":     ("Soporte Técnico",       "Developer", 1486084669320724480),
    "reclamar_beneficios": ("Reclamar Beneficios",   "Vip",       1486084827080822865),
    "solicitar_superiores":("Solicitar Superiores",  "Owner",     1486085037693734962),
}

async def enviar_panel_tickets(canal, guild):
    e = discord.Embed(title="🎫  Centro de Soporte",
                      description=f"¡Bienvenido al sistema de tickets de **{guild.name}**!\n\n"
                                  "Seleccioná la categoría correspondiente en el menú de abajo.\n"
                                  "Un miembro del staff te atenderá a la brevedad.",
                      color=discord.Color.from_str("#5865F2"))
    if guild.icon: e.set_thumbnail(url=guild.icon.url)
    e.add_field(name="<:Member:1486085000117092382>  Soporte General",     value="Consultas generales del servidor.",          inline=False)
    e.add_field(name="<:Developer:1486084669320724480>  Soporte Técnico",  value="Problemas técnicos o bugs.",                 inline=False)
    e.add_field(name="<:Vip:1486084827080822865>  Reclamar Beneficios",    value="Reclamá tus beneficios VIP u otros premios.",inline=False)
    e.add_field(name="<:Owner:1486085037693734962>  Solicitar Superiores", value="Contacto directo con la administración.",    inline=False)
    e.set_footer(text=f"{guild.name}  •  Solo abrí un ticket si realmente lo necesitás.",
                 icon_url=guild.icon.url if guild.icon else None)
    await canal.send(embed=e, view=TicketPanelView())

class CerrarTicketModal(discord.ui.Modal, title="🔒 Cerrar ticket"):
    motivo = discord.ui.TextInput(label="Motivo del cierre", style=discord.TextStyle.paragraph, max_length=300)

    async def on_submit(self, i: discord.Interaction):
        tdata = cargar_tickets(); ch_id = str(i.channel_id); info = tdata["tickets"].get(ch_id)
        e = discord.Embed(title="🔒 Ticket cerrado",
                          description="Cerrado por el staff. El canal se eliminará en **5 segundos**.",
                          color=COLORES["ban"], timestamp=datetime.now(timezone.utc))
        e.add_field(name="👮 Cerrado por", value=i.user.mention,                                                     inline=True)
        e.add_field(name="📋 Tipo",        value=info.get("tipo","?") if info else "?",                             inline=True)
        e.add_field(name="🆔 Número",      value=f"`#{info.get('numero','?')}`" if info else "?",                   inline=True)
        e.add_field(name="📝 Motivo",      value=self.motivo.value,                                                 inline=False)
        e.set_footer(text=ts())
        await i.response.send_message(embed=e)
        if ch_id in tdata["tickets"]: del tdata["tickets"][ch_id]; guardar_tickets(tdata)
        await asyncio.sleep(5)
        try: await i.channel.delete()
        except: pass

class TicketActionView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="✋ Reclamar ticket", style=discord.ButtonStyle.success, custom_id="ticket_claim_btn")
    async def claim_btn(self, i: discord.Interaction, b):
        if not es_staff(i.user): return await i.response.send_message("❌ Solo el staff puede reclamar tickets.", ephemeral=True)
        tdata = cargar_tickets(); info = tdata["tickets"].get(str(i.channel_id))
        if info: info["reclamado_por"] = str(i.user.id); guardar_tickets(tdata)
        e = discord.Embed(title="✋ Ticket reclamado",
                          description=f"{i.user.mention} tomó a cargo este ticket y lo atenderá a la brevedad.",
                          color=COLORES["ok"], timestamp=datetime.now(timezone.utc))
        e.set_author(name=str(i.user), icon_url=i.user.display_avatar.url); e.set_footer(text=ts())
        await i.response.send_message(embed=e)

    @discord.ui.button(label="🔒 Cerrar ticket", style=discord.ButtonStyle.danger, custom_id="ticket_close_btn")
    async def close_btn(self, i: discord.Interaction, b):
        if not es_staff(i.user): return await i.response.send_message("❌ Solo el staff puede cerrar tickets.", ephemeral=True)
        await i.response.send_modal(CerrarTicketModal())

class TicketSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="📋  Seleccioná el tipo de ticket...", min_values=1, max_values=1,
                         custom_id="ticket_panel_select", options=[
            discord.SelectOption(label="Soporte General",      value="soporte_general",      emoji=discord.PartialEmoji(name="member",    id=1485682448300904668), description="Consultas generales"),
            discord.SelectOption(label="Soporte Técnico",      value="soporte_tecnico",      emoji=discord.PartialEmoji(name="Developer",  id=1485682311373656326), description="Problemas técnicos o bugs"),
            discord.SelectOption(label="Reclamar Beneficios",  value="reclamar_beneficios",  emoji=discord.PartialEmoji(name="Vip",        id=1485682412179554355), description="Beneficios VIP u otros premios"),
            discord.SelectOption(label="Solicitar Superiores", value="solicitar_superiores", emoji=discord.PartialEmoji(name="Owner",      id=1485682488952098917), description="Contactar administración"),
        ])

    async def callback(self, i: discord.Interaction):
        tipo_nombre, emoji_name, emoji_id = TIPOS_TICKET[self.values[0]]
        tdata = cargar_tickets(); uid = str(i.user.id)
        for ch_id, info in list(tdata["tickets"].items()):
            if info.get("user_id") == uid:
                c = i.guild.get_channel(int(ch_id))
                if c: return await i.response.send_message(f"❌ Ya tenés un ticket abierto: {c.mention}", ephemeral=True)
                del tdata["tickets"][ch_id]; guardar_tickets(tdata); break
        tdata["counter"] += 1; numero = f"{tdata['counter']:03d}"
        overwrites = {
            i.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            i.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
        }
        role = i.guild.get_role(STAFF_ROLE_ID)
        if role: overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
        categoria = i.guild.get_channel(1466491475436245220)
        try:
            canal = await i.guild.create_text_channel(f"ticket-{numero}", overwrites=overwrites, category=categoria,
                                                       reason=f"Ticket #{numero} — {i.user} — {tipo_nombre}")
        except discord.Forbidden: return await i.response.send_message("❌ Sin permisos para crear el canal.", ephemeral=True)
        tdata["tickets"][str(canal.id)] = {"user_id": uid, "tipo": tipo_nombre, "numero": numero, "guild_id": str(i.guild.id), "fecha": ts()}
        guardar_tickets(tdata)
        e = discord.Embed(title=f"<:{emoji_name}:{emoji_id}>  Ticket #{numero} — {tipo_nombre}",
                          description=f"¡Hola {i.user.mention}! Tu ticket fue creado.\nDescribí tu consulta con el mayor detalle posible.",
                          color=discord.Color.from_str("#5865F2"), timestamp=datetime.now(timezone.utc))
        e.set_thumbnail(url=i.user.display_avatar.url)
        e.add_field(name="👤 Abierto por", value=f"{i.user.mention} (`{i.user}`)", inline=True)
        e.add_field(name="📋 Categoría",   value=tipo_nombre,                      inline=True)
        e.add_field(name="🆔 Número",      value=f"`#{numero}`",                   inline=True)
        e.add_field(name="📌 Instrucciones",
                    value="• Describí tu caso claramente.\n• Adjuntá capturas si es necesario.\n• Sé respetuoso con el staff.", inline=False)
        e.set_footer(text=f"Abierto el {ts()}")
        await canal.send(content=f"{i.user.mention} — <@&{STAFF_ROLE_ID}>", embed=e, view=TicketActionView())
        await i.response.send_message(f"✅ Ticket creado correctamente: {canal.mention}", ephemeral=True)

class TicketPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.add_item(TicketSelect())

# --- Eventos ---
@bot.event
async def on_member_join(member: discord.Member):
    canal_bv = member.guild.get_channel(CANAL_BIENVENIDA)
    if canal_bv:
        menciones = " · ".join(f"<#{cid}>" for cid in CANALES_RECOMENDADOS)
        e = discord.Embed(title=f"¡Bienvenido/a a {member.guild.name}! 🎉",
                          description=f"Hola {member.mention}, ¡nos alegra tenerte acá!\nSos el miembro número **{member.guild.member_count}**.",
                          color=discord.Color.from_str("#5865F2"), timestamp=datetime.now(timezone.utc))
        e.set_thumbnail(url=member.display_avatar.url)
        if member.guild.icon: e.set_author(name=member.guild.name, icon_url=member.guild.icon.url)
        e.add_field(name="👤 Usuario",              value=f"`{member}` — `{member.id}`",          inline=True)
        e.add_field(name="📅 Cuenta creada",        value=member.created_at.strftime("%d/%m/%Y"), inline=True)
        e.add_field(name="📌 Canales recomendados", value=menciones,                              inline=False)
        e.set_footer(text="¡Esperamos que disfrutes tu estadía!")
        try: await canal_bv.send(content=member.mention, embed=e)
        except: pass
    if member.guild.id not in raid_guilds: return
    try:
        await member.timeout(discord.utils.utcnow() + timedelta(minutes=30), reason="[Raid Mode] Auto-silencio")
        e = discord.Embed(title="🛡️ Raid Mode — Miembro silenciado",
                          description=f"{member.mention} silenciado 30 min por raid mode.",
                          color=COLORES["mute"], timestamp=datetime.now(timezone.utc))
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="👤 Usuario", value=f"`{member}` — `{member.id}`",          inline=True)
        e.add_field(name="📅 Cuenta",  value=member.created_at.strftime("%d/%m/%Y"), inline=True)
        e.set_footer(text="Usá /unmute si es legítimo.")
        c = member.guild.get_channel(CANAL_STAFF_LOGS)
        if c: await c.send(embed=e)
    except: pass

@bot.event
async def on_ready():
    bot.add_view(TicketPanelView())
    bot.add_view(TicketActionView())
    await tree.sync()
    print(f"✅ {bot.user} listo | Servidores: {len(bot.guilds)}")

class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self, *a): pass

def _start_health():
    port = int(os.getenv("PORT", 10000))
    HTTPServer(("0.0.0.0", port), _Health).serve_forever()

threading.Thread(target=_start_health, daemon=True).start()
bot.run(TOKEN)
