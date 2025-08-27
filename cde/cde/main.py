import os
import json
import random
import string
import threading
import logging
from functools import wraps
from typing import Dict, Any, List, Optional
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, error
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# --- Configuración y Constantes ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# TOKEN DIRECTO (no seguro, pero funciona sin variables de entorno)
TOKEN: Optional[str] = "8045744571:AAH1mxU7O76KuItF_mxD-mJWlK6zRdMmyAM"
ADMIN: int = 7590578210

if not TOKEN:
    logging.error("❌ No se encontró el token de Telegram.")
    exit()

BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
DB_USERS: str = os.path.join(BASE_DIR, "users.json")
DB_STOCK: str = os.path.join(BASE_DIR, "stock.json")
DB_KEYS: str = os.path.join(BASE_DIR, "claves.json")
DB_BANS: str = os.path.join(BASE_DIR, "ban_users.json")
DB_ADMINS: str = os.path.join(BASE_DIR, "admins.json")
DB_CARDS: str = os.path.join(BASE_DIR, "cards.json")
DB_CARD_KEYS: str = os.path.join(BASE_DIR, "card_keys.json")

# GIFs para el mensaje de inicio
START_MEDIA = [
    "https://64.media.tumblr.com/bff8a385b75b4f747ad5de78a917faae/99c3bba1a6801134-82/s540x810/7d5a2b6b57fb0ea5c61e41a935990618ec78669d.gif",
    "https://i.pinimg.com/originals/dc/d6/2f/dcd62f5fe32b1cabae1f89626c30fef6.gif",
    "https://i.pinimg.com/originals/cb/26/25/cb262560dbf553b91deeec5bd35d216b.gif",
    "https://giffiles.alphacoders.com/222/222779.gif",
    "https://giffiles.alphacoders.com/222/222779.gif",
    "https://i.pinimg.com/originals/dc/d6/2f/dcd62f5fe32b1cabae1f89626c30fef6.gif",
    "https://i.pinimg.com/originals/dc/d6/2f/dcd62f5fe32b1cabae1f89626c30fef6.gif",
]

# Estados para ConversationHandler
AWAITING_USER_ID_TO_REVOKE, AWAITING_STOCK_SITE, AWAITING_STOCK_MESSAGE, AWAITING_STOCK_ACCOUNTS, AWAITING_CARDS_SITE, AWAITING_CARDS_MESSAGE, AWAITING_CARDS_ACCOUNTS, AWAITING_ADMIN_ID, AWAITING_REMOVE_ADMIN_ID, BROADCAST_CONTENT, AWAITING_USER_ID_TO_BAN, AWAITING_USER_ID_TO_UNBAN = range(12)

# --- Servidor Keep-Alive para Replit ---
_keep = Flask(__name__)

@_keep.get("/")
def _health():
    """Responde 'OK' para mantener el servidor activo."""
    return "OK", 200

def _run_keep_alive():
    """Ejecuta el servidor Flask en un hilo separado."""
    port = int(os.environ.get("PORT", 8000))
    _keep.run(host="0.0.0.0", port=port)

threading.Thread(target=_run_keep_alive, daemon=True).start()
# --- Fin Keep-Alive ---

# --- Funciones de Utilidad para Base de Datos ---
def load_data(path: str, default: Optional[Any] = None) -> Any:
    """
    Carga datos de un archivo JSON.
    Retorna el valor por defecto si el archivo no existe o hay un error.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logging.warning(f"Archivo no encontrado o con formato incorrecto: {path}")
        return default or {} if isinstance(default, dict) else default or []

def save_data(path: str, data: Any):
    """Guarda datos en un archivo JSON de forma segura."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    logging.info(f"Datos guardados en {path}")


# --- Decoradores para Verificación de Usuarios ---
def is_banned(user_id: int) -> bool:
    """Verifica si un usuario está baneado."""
    banned_users = load_data(DB_BANS, default=[])
    return user_id in banned_users

def is_admin(user_id: int) -> bool:
    """Verifica si un usuario tiene privilegios de administrador."""
    admins = load_data(DB_ADMINS, default=[])
    return user_id == ADMIN or user_id in admins

def check_ban(func):
    """Decorador para restringir el acceso a usuarios baneados."""
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else None
        if not user_id:
            return

        if user_id != ADMIN and is_banned(user_id):
            if update.effective_message:
                await update.effective_message.reply_text(
                    text="🚫 <b>Estás baneado y no puedes usar este bot.</b>",
                    parse_mode="HTML"
                )
            else:
                await update.callback_query.answer("🚫 Estás baneado y no puedes usar este bot.", show_alert=True)
            return
        return await func(update, ctx)
    return wrapper

def check_admin(func):
    """Decorador para restringir el acceso a usuarios admin y super admin."""
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else None
        if not user_id:
            return

        if not is_admin(user_id):
            if update.effective_message:
                await update.effective_message.reply_text("❌ No autorizado.")
            else:
                await update.callback_query.answer("❌ No autorizado.", show_alert=True)
            return
        return await func(update, ctx)
    return wrapper

def check_super_admin(func):
    """Decorador para restringir el acceso solo al creador del bot (ADMIN)."""
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else None
        if not user_id:
            return

        if user_id != ADMIN:
            if update.effective_message:
                await update.effective_message.reply_text("❌ No autorizado.")
            else:
                await update.callback_query.answer("❌ No autorizado.", show_alert=True)
            return
        return await func(update, ctx)
    return wrapper


# --- Teclados de Botones ---
def kb_start(uid: int) -> InlineKeyboardMarkup:
    """Genera el teclado de inicio, incluyendo el panel de admin si el usuario es el admin."""
    kb = [
        [
            InlineKeyboardButton("👤 Perfil", callback_data="profile"),
            InlineKeyboardButton("📦 Stock", callback_data="stock"),
            InlineKeyboardButton("📖 Comandos", callback_data="cmds"),
        ]
    ]
    if is_admin(uid):
        kb.append([InlineKeyboardButton("⚙️ Panel Admin", callback_data="panel")])
    return InlineKeyboardMarkup(kb)

KB_ADMIN = InlineKeyboardMarkup([
    [InlineKeyboardButton("🔐 Crear claves", callback_data="gen_cmd")],
    [InlineKeyboardButton("💎 SuperPro Key", callback_data="super_pro_key")],
    [InlineKeyboardButton("❌ Quitar plan premium", callback_data="revoke_premium_start")],
    [InlineKeyboardButton("👥 Ver usuarios", callback_data="users_cmd")],
    [InlineKeyboardButton("🚫 Banear usuario", callback_data="ban_user_start")],
    [InlineKeyboardButton("✅ Desbanear usuario", callback_data="unban_user_start")],
    [InlineKeyboardButton("➕ Subir Cuentas", callback_data="addstock_start")],
    [InlineKeyboardButton("➕ Subir Tarjetas", callback_data="addcards_start")],
    [InlineKeyboardButton("💳 Keys Tarjetas", callback_data="gen_cards_key")],
    [InlineKeyboardButton("📢 Enviar Anuncio", callback_data="send_msg_cmd")],
    [InlineKeyboardButton("👑 Promover Admin", callback_data="add_admin_start")],
    [InlineKeyboardButton("💀 Degradar Admin", callback_data="rem_admin_start")]
])

KB_STOCK_MENU = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("✅ Cuentas Premium", callback_data="show_stock_cuentas"),
        InlineKeyboardButton("💳 Tarjetas", callback_data="show_stock_tarjetas")
    ],
    [
        InlineKeyboardButton("⏪ Regresar", callback_data="start_menu")
    ]
])

KB_RETURN_TO_START = InlineKeyboardMarkup([
    [InlineKeyboardButton("⏪ Regresar", callback_data="start_menu")]
])

# --- Comandos de Inicio y Ayuda ---
@check_ban
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start y notifica al admin sobre el nuevo usuario."""
    uid = update.effective_user.id
    user_info = update.effective_user

    users = load_data(DB_USERS, {})
    is_new_user = False
    if str(uid) not in users:
        users[str(uid)] = {
            "plan_normal": {"nombre": "Sin plan", "max": 0, "usados": 0},
            "plan_tarjetas": {"nombre": "Sin plan", "max": 0, "usados": 0},
            "invalid_key_attempts": 0
        }
        save_data(DB_USERS, users)
        is_new_user = False # El usuario es nuevo, pero lo manejo como no nuevo para evitar notificaciones excesivas

    # Asegura que la estructura de datos esté completa para todos los usuarios
    user_data = users.get(str(uid), {})
    if "plan_normal" not in user_data:
        user_data["plan_normal"] = {"nombre": "Sin plan", "max": 0, "usados": 0}
    if "plan_tarjetas" not in user_data:
        user_data["plan_tarjetas"] = {"nombre": "Sin plan", "max": 0, "usados": 0}
    if "invalid_key_attempts" not in user_data:
        user_data["invalid_key_attempts"] = 0
    users[str(uid)] = user_data
    save_data(DB_USERS, users)


    if is_new_user and uid != ADMIN:
        try:
            admin_message = (
                f"🎉 <b>Nuevo usuario ha iniciado el bot:</b>\n"
                f"🆔 ID: <code>{user_info.id}</code>\n"
                f"👤 Nombre: <code>{user_info.first_name}</code>\n"
                f"🔗 Username: @{user_info.username or 'N/A'}"
            )
            await ctx.bot.send_message(chat_id=ADMIN, text=admin_message, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Error al enviar mensaje al admin: {e}")

    gif_url = random.choice(START_MEDIA)
    caption_text = (
        f"<u><b>🎉 Bienvenido a PAUBLITE_GT</b></u>\n\n"
        f"<b>🆔 Tu ID:</b> <code>{user_info.id}</code>\n"
        f"<b>👤 Tu Nombre:</b> <code>{user_info.first_name}</code>\n"
        f"<b>🔗 Tu Username:</b> @{user_info.username or 'N/A'}\n\n"
        f"<b>💳 Compra claves premium aquí 👉 @PAUBLITE_GT @deluxeGt @NigerianStore</b>\n"
        f"<b>🔗 Canal Oficial:</b> https://t.me/+kpO7XeoQsDQ0MWM0\n\n"
        f"<b>📌 Comandos:</b>\n"
        f"  - <code>/key CLAVE</code>\n"
        f"  - <code>/get sitio cant</code>\n\n"
        f"<b>📌 Administración:</b> Panel abajo"
    )

    try:
        await ctx.bot.send_animation(
            chat_id=update.effective_chat.id,
            animation=gif_url,
            caption=caption_text,
            parse_mode="HTML",
            reply_markup=kb_start(uid)
        )
    except error.BadRequest as e:
        logging.error(f"Error al enviar animación: {e}. Intentando enviar como foto...")
        await ctx.bot.send_message(
            chat_id=update.effective_chat.id,
            text=caption_text,
            parse_mode="HTML",
            reply_markup=kb_start(uid)
        )

# --- Comandos de Usuario ---
@check_ban
async def key_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /key para activar una clave."""
    if not ctx.args:
        await update.effective_chat.send_message(
            text="🤖 <b>Uso:</b>\n<code>/key CLAVE</code>\n\n💎 Compra claves premium\n👉 @PAUBLITE_GT @deluxeGt @NigerianStore\n",
            parse_mode="HTML"
        )
        return

    clave = ctx.args[0].strip()
    claves = load_data(DB_KEYS, {})
    card_keys = load_data(DB_CARD_KEYS, {})
    uid = str(update.effective_user.id)
    users = load_data(DB_USERS, {})
    banned_users = load_data(DB_BANS, default=[])

    # Asegura que la estructura de datos del usuario esté completa
    user_data = users.get(uid)
    if not user_data:
        user_data = {
            "plan_normal": {"nombre": "Sin plan", "max": 0, "usados": 0},
            "plan_tarjetas": {"nombre": "Sin plan", "max": 0, "usados": 0},
            "invalid_key_attempts": 0
        }
        users[uid] = user_data
    else:
        if "plan_normal" not in user_data:
            user_data["plan_normal"] = {"nombre": "Sin plan", "max": 0, "usados": 0}
        if "plan_tarjetas" not in user_data:
            user_data["plan_tarjetas"] = {"nombre": "Sin plan", "max": 0, "usados": 0}
        if "invalid_key_attempts" not in user_data:
            user_data["invalid_key_attempts"] = 0

    save_data(DB_USERS, users) # Guarda la estructura de datos actualizada

    is_card_key = clave in card_keys
    is_normal_key = clave in claves

    if is_normal_key:
        # Lógica para canjear clave normal
        if user_data.get("plan_normal", {}).get("nombre") != "Sin plan" and user_data.get("plan_normal", {}).get("max", 0) > user_data.get("plan_normal", {}).get("usados", 0):
            await update.effective_chat.send_message(
                text="❌ <b>Ya tienes un plan de cuentas activo.</b>\nNo puedes activar otra clave hasta que termines tus usos actuales.",
                parse_mode="HTML"
            )
            return

        plan, maxi = claves.pop(clave)
        save_data(DB_KEYS, claves)
        user_data["plan_normal"]["nombre"] = plan
        user_data["plan_normal"]["max"] = maxi
        user_data["plan_normal"]["usados"] = 0
        save_data(DB_USERS, users)

        await update.effective_chat.send_message(
            text=(
                f"✨ <b>¡Felicidades!</b> 🎉\n"
                f"Has activado una nueva clave premium. Se ha activado el plan <b>{plan}</b> con <b>{maxi}</b> usos."
            ),
            parse_mode="HTML"
        )
        return

    elif is_card_key:
        # Lógica para canjear clave de tarjetas
        if user_data.get("plan_tarjetas", {}).get("nombre") != "Sin plan" and user_data.get("plan_tarjetas", {}).get("max", 0) > user_data.get("plan_tarjetas", {}).get("usados", 0):
            await update.effective_chat.send_message(
                text="❌ <b>Ya tienes un plan de tarjetas activo.</b>\nNo puedes activar otra clave hasta que termines tus usos actuales.",
                parse_mode="HTML"
            )
            return

        plan, maxi = card_keys.pop(clave)
        save_data(DB_CARD_KEYS, card_keys)
        user_data["plan_tarjetas"]["nombre"] = plan
        user_data["plan_tarjetas"]["max"] = maxi
        user_data["plan_tarjetas"]["usados"] = 0
        save_data(DB_USERS, users)

        await update.effective_chat.send_message(
            text=(
                f"✨ <b>¡Felicidades!</b> 🎉\n"
                f"Has activado un nuevo plan para acceder a tarjetas. Se ha activado el plan <b>{plan}</b> con <b>{maxi}</b> usos."
            ),
            parse_mode="HTML"
        )
        return

    else:
        # Lógica para clave inválida
        user_data["invalid_key_attempts"] = user_data.get("invalid_key_attempts", 0) + 1
        save_data(DB_USERS, users)

        if user_data["invalid_key_attempts"] >= 3:
            if int(uid) not in banned_users:
                banned_users.append(int(uid))
                save_data(DB_BANS, banned_users)

            await update.effective_chat.send_message(
                text="🚫 <b>¡Has sido baneado!</b> Demasiados intentos fallidos con claves inválidas. No puedes usar más este bot.",
                parse_mode="HTML"
            )
            return

        await update.effective_chat.send_message(
            text=(
                f"❌ <b>Clave inválida. No insistas o serás baneado.</b>\n"
                f"Intentos restantes: {3 - user_data['invalid_key_attempts']}\n\n"
                "<b>💳 Compra claves premium</b> con un mensaje a:\n"
                "🔗 @PAUBLITE_GT @deluxeGt @NigerianStore\n"
            ),
            parse_mode="HTML"
        )
        return

@check_ban
async def get_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /get para obtener cuentas."""
    if len(ctx.args) < 2:
        await update.effective_chat.send_message(text="Uso: /get sitio cantidad")
        return

    sitio = ctx.args[0].strip().lower()
    try:
        cant = int(ctx.args[1])
    except ValueError:
        await update.effective_chat.send_message(text="Cantidad debe ser un número.")
        return

    uid = str(update.effective_user.id)
    users = load_data(DB_USERS, {})
    user_data = users.get(uid)

    if not user_data or (user_data.get("plan_normal", {}).get("nombre") == "Sin plan" and user_data.get("plan_tarjetas", {}).get("nombre") == "Sin plan"):
        await update.effective_chat.send_message(text="❌ Sin plan activo.")
        return

    # --- LÓGICA PARA BUSCAR STOCK DE CUENTAS ---
    stock = load_data(DB_STOCK, {})
    cuentas_disponibles = None

    # Busca la clave de forma insensible a mayúsculas y minúsculas
    for key in stock.keys():
        if key.lower() == sitio:
            cuentas_disponibles = stock.get(key)
            sitio = key  # Usa la clave original para mostrar el nombre
            break

    # Si se encontró el stock de cuentas
    if cuentas_disponibles:
        plan_normal = user_data.get("plan_normal", {})
        if plan_normal.get("nombre") == "Sin plan":
            await update.effective_chat.send_message(
                text="❌ Necesitas una clave premium normal para acceder a este stock."
            )
            return

        disp = plan_normal.get("max", 0) - plan_normal.get("usados", 0)
        if cant > disp:
            await update.effective_chat.send_message(text=f"❌ Te quedan {disp} accesos.")
            return

        # Verifica si el stock está en el nuevo formato (diccionario)
        if isinstance(cuentas_disponibles, dict) and "accounts" in cuentas_disponibles:
            accounts_list = cuentas_disponibles.get("accounts", [])
            usage_message = cuentas_disponibles.get("message", "")

            if not accounts_list or len(accounts_list) < cant:
                await update.effective_chat.send_message(text=f"❌ Sin stock suficiente para {sitio}.")
                return

            cuentas_a_enviar = accounts_list[:cant]
            stock[sitio]["accounts"] = accounts_list[cant:] # Obtenemos el resto de las cuentas

            if not cuentas_a_enviar:
                await update.effective_chat.send_message(text=f"❌ Sin stock suficiente para {sitio}.")
                return

            plan_normal["usados"] = plan_normal.get("usados", 0) + cant
            save_data(DB_STOCK, stock)
            save_data(DB_USERS, users)

            for cuenta_data in cuentas_a_enviar:
                account_info = cuenta_data.get("account", "N/A")
                file_id = cuenta_data.get("file_id")
                file_type = cuenta_data.get("file_type")

                final_text = (
                    f"🎁 <b>{sitio.upper()}</b>\n\n"
                    f"✨ Cuenta: <code>{account_info}</code>\n"
                    f"<i>{usage_message}</i>\n\n"
                    f"Usos: {plan_normal['usados']}/{plan_normal['max']}"
                )

                if file_id and file_type:
                    try:
                        if file_type == 'photo':
                            await ctx.bot.send_photo(
                                chat_id=update.effective_chat.id,
                                photo=file_id,
                                caption=final_text,
                                parse_mode="HTML"
                            )
                        elif file_type == 'video':
                            await ctx.bot.send_video(
                                chat_id=update.effective_chat.id,
                                video=file_id,
                                caption=final_text,
                                parse_mode="HTML"
                            )
                        elif file_type == 'animation':
                            await ctx.bot.send_animation(
                                chat_id=update.effective_chat.id,
                                animation=file_id,
                                caption=final_text,
                                parse_mode="HTML"
                            )
                    except Exception as e:
                        logging.error(f"Error al enviar el archivo {file_type}: {e}. Enviando como texto...")
                        await update.effective_chat.send_message(text=final_text, parse_mode="HTML")
                else:
                    await update.effective_chat.send_message(text=final_text, parse_mode="HTML")
        else: # Formato de lista de texto antiguo
            if not cuentas_disponibles or len(cuentas_disponibles) < cant:
                await update.effective_chat.send_message(text=f"❌ Sin stock suficiente para {sitio}.")
                return

            cuentas = cuentas_disponibles[:cant]
            stock[sitio] = cuentas_disponibles[cant:]
            plan_normal["usados"] = plan_normal.get("usados", 0) + cant
            save_data(DB_STOCK, stock)
            save_data(DB_USERS, users)

            texto = "\n".join([f"✨ <code>{c}</code>" for c in cuentas])
            await update.effective_chat.send_message(
                text=f"🎁 <b>{sitio.upper()}</b> ×{cant}\n\n{texto}\n\nUsos: {plan_normal['usados']}/{plan_normal['max']}",
                parse_mode="HTML"
            )
        return

    # --- Lógica para obtener stock de TARJETAS ---
    cards = load_data(DB_CARDS, {})
    tarjetas_disponibles = None

    # Busca la clave de forma insensible a mayúsculas y minúsculas
    for key in cards.keys():
        if key.lower() == sitio:
            tarjetas_disponibles = cards.get(key)
            sitio = key  # Usa la clave original para mostrar el nombre
            break

    if tarjetas_disponibles:
        plan_tarjetas = user_data.get("plan_tarjetas", {})
        if plan_tarjetas.get("nombre") == "Sin plan":
            await update.effective_chat.send_message(
                text="❌ Necesitas una clave de tarjetas para acceder a este stock."
            )
            return

        disp = plan_tarjetas.get("max", 0) - plan_tarjetas.get("usados", 0)
        if cant > disp:
            await update.effective_chat.send_message(text=f"❌ Te quedan {disp} accesos para tarjetas.")
            return

        # Verifica si el stock de tarjetas está en el nuevo formato (diccionario)
        if isinstance(tarjetas_disponibles, dict) and "cards" in tarjetas_disponibles:
            card_list = tarjetas_disponibles.get("cards", [])
            usage_message = tarjetas_disponibles.get("message", "")

            if not card_list or len(card_list) < cant:
                await update.effective_chat.send_message(text=f"❌ Sin stock de tarjetas suficiente para {sitio}.")
                return

            tarjetas_a_enviar = card_list[:cant]
            cards[sitio]["cards"] = card_list[cant:]

            plan_tarjetas["usados"] = plan_tarjetas.get("usados", 0) + cant
            save_data(DB_CARDS, cards)
            save_data(DB_USERS, users)

            for tarjeta_data in tarjetas_a_enviar:
                card_info = tarjeta_data.get("card", "N/A")
                file_id = tarjeta_data.get("file_id")
                file_type = tarjeta_data.get("file_type")

                final_text = (
                    f"🎁 <b>{sitio.upper()}</b>\n\n"
                    f"💳 Tarjeta: <code>{card_info}</code>\n"
                    f"<i>{usage_message}</i>\n\n"
                    f"Usos: {plan_tarjetas['usados']}/{plan_tarjetas['max']}"
                )

                if file_id and file_type:
                    try:
                        if file_type == 'photo':
                            await ctx.bot.send_photo(
                                chat_id=update.effective_chat.id,
                                photo=file_id,
                                caption=final_text,
                                parse_mode="HTML"
                            )
                        elif file_type == 'video':
                            await ctx.bot.send_video(
                                chat_id=update.effective_chat.id,
                                video=file_id,
                                caption=final_text,
                                parse_mode="HTML"
                            )
                        elif file_type == 'animation':
                            await ctx.bot.send_animation(
                                chat_id=update.effective_chat.id,
                                animation=file_id,
                                caption=final_text,
                                parse_mode="HTML"
                            )
                    except Exception as e:
                        logging.error(f"Error al enviar el archivo {file_type}: {e}. Enviando como texto...")
                        await update.effective_chat.send_message(text=final_text, parse_mode="HTML")
                else:
                    await update.effective_chat.send_message(text=final_text, parse_mode="HTML")

        else: # Formato de lista de texto antiguo
            if not tarjetas_disponibles or len(tarjetas_disponibles) < cant:
                await update.effective_chat.send_message(text=f"❌ Sin stock de tarjetas suficiente para {sitio}.")
                return

            tarjetas = tarjetas_disponibles[:cant]
            cards[sitio] = tarjetas_disponibles[cant:]
            plan_tarjetas["usados"] = plan_tarjetas.get("usados", 0) + cant
            save_data(DB_CARDS, cards)
            save_data(DB_USERS, users)

            texto = "\n".join([f"💳 <code>{t}</code>" for t in tarjetas])
            await update.effective_chat.send_message(
                text=f"🎁 <b>{sitio.upper()}</b> ×{cant}\n\n{texto}\n\nUsos: {plan_tarjetas['usados']}/{plan_tarjetas['max']}",
                parse_mode="HTML"
            )
        return

    await update.effective_chat.send_message(text=f"❌ Sin stock suficiente para <b>{sitio}</b>.", parse_mode="HTML")

# --- Manejador genérico para mensajes no reconocidos ---
async def handle_unknown_messages(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Responde a mensajes que no son comandos."""
    await update.message.reply_text(
        "❌ Lo siento, no entiendo ese comando. Usa <code>/start</code> para ver el menú principal.\n\n"
        "<b>💳 Compra acceso premium aquí</b> 👉 @PAUBLITE_GT @deluxeGt @NigerianStore",
        parse_mode="HTML"
    )

# --- Funciones de Callback para Botones ---
async def return_to_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Regresa al menú de inicio."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    gif_url = random.choice(START_MEDIA)
    caption_text = (
        f"<u><b>🎉 Bienvenido de nuevo a PAUBLITE_GT</b></u>\n\n"
        f"<b>ID:</b> <code>{uid}</code>\n"
        f"<b>Compra claves premium aquí 👉 @PAUBLITE_GT @deluxeGt @NigerianStore</b>\n"
        f"<b>Canal Oficial:</b> https://t.me/+kpO7XeoQsDQ0MWM0\n\n"
    )

    await query.edit_message_caption(
        caption=caption_text,
        parse_mode="HTML",
        reply_markup=kb_start(uid)
    )

async def show_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Muestra el perfil del usuario."""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    users = load_data(DB_USERS, {})
    user_data = users.get(user_id)

    if not user_data:
        await query.edit_message_caption(
            caption="❌ No se encontró tu perfil. Intenta reiniciar con /start.",
            reply_markup=KB_RETURN_TO_START
        )
        return

    plan_normal = user_data.get('plan_normal', {"nombre": "Sin plan", "usados": 0, "max": 0})
    plan_tarjetas = user_data.get('plan_tarjetas', {"nombre": "Sin plan", "usados": 0, "max": 0})

    profile_text = (
        f"<u><b>👤 PERFIL DE USUARIO</b></u>\n\n"
        f"<b>🆔 ID:</b> <code>{user_id}</code>\n"
        f"<b>👤 Nombre:</b> <code>{query.from_user.full_name}</code>\n"
        f"<b>🔗 Username:</b> @{query.from_user.username or 'N/A'}\n"
        f"<b>Plan Cuentas:</b> <i>{plan_normal['nombre']}</i>\n"
        f"<b>Usos:</b> {plan_normal['usados']}/{plan_normal['max']}\n\n"
        f"<b>Plan Tarjetas:</b> <i>{plan_tarjetas['nombre']}</i>\n"
        f"<b>Usos:</b> {plan_tarjetas['usados']}/{plan_tarjetas['max']}\n"
    )

    await query.edit_message_caption(
        caption=profile_text,
        parse_mode="HTML",
        reply_markup=KB_RETURN_TO_START
    )

async def show_cmds(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Muestra la lista de comandos."""
    query = update.callback_query
    await query.answer()

    text = (
        f"<u><b>📖 COMANDOS DISPONIBLES</b></u>\n\n"
        f"<b>• /start</b> - Inicia el bot y muestra el menú principal.\n"
        f"<b>• /key &lt;clave&gt;</b> - Activa una clave premium para obtener usos.\n"
        f"<b>• /get &lt;sitio&gt; &lt;cantidad&gt;</b> - Obtiene cuentas del stock. Ej: <code>/get netflix 1</code>\n"
    )

    await query.edit_message_caption(
        caption=text,
        parse_mode="HTML",
        reply_markup=KB_RETURN_TO_START
    )

async def show_admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Muestra el panel de administración."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_caption(
        caption="<u><b>⚙️ PANEL DE ADMINISTRACIÓN</b></u>\n\n"
                "Selecciona una opción para gestionar el bot.",
        parse_mode="HTML",
        reply_markup=KB_ADMIN
    )

# --- Lógica de Stock Separada ---
async def show_stock_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Muestra el menú para elegir entre stock de cuentas o tarjetas."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_caption(
        caption="<u><b>📦 Selecciona el tipo de stock que deseas ver:</b></u>",
        parse_mode="HTML",
        reply_markup=KB_STOCK_MENU
    )

async def show_cuentas_stock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Muestra el stock de cuentas premium."""
    query = update.callback_query
    await query.answer()

    stock = load_data(DB_STOCK, {})
    message = "<u><b>✅ STOCK DE CUENTAS DISPONIBLES</b></u>\n\n"

    if not stock:
        message += "❌ No hay stock disponible de cuentas en este momento."
    else:
        for site, data in stock.items():
            if isinstance(data, list):
                count = len(data)
            else:
                count = len(data.get("accounts", []))
            message += f"<b>{site.upper()}</b> → <b>{count}</b> cuentas\n"

    await query.edit_message_caption(
        caption=message,
        parse_mode="HTML",
        reply_markup=KB_RETURN_TO_START
    )

async def show_cards_stock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Muestra el stock de tarjetas."""
    query = update.callback_query
    await query.answer()

    cards = load_data(DB_CARDS, {})
    message = "<u><b>💳 STOCK DE TARJETAS DISPONIBLES</b></u>\n\n"

    if not cards:
        message += "❌ No hay stock disponible de tarjetas en este momento."
    else:
        for bank, data in cards.items():
            if isinstance(data, list):
                count = len(data)
            else:
                count = len(data.get("cards", []))
            message += f"<b>{bank.upper()}</b> → <b>{count}</b> tarjetas\n"

    await query.edit_message_caption(
        caption=message,
        parse_mode="HTML",
        reply_markup=KB_RETURN_TO_START
    )

# --- Comandos de Admin ---
@check_admin
async def gen_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /gen para generar claves de activación con un formato específico."""
    claves = load_data(DB_KEYS, {})
    planes = [
        (1, "Bronce 1"),
        (2, "Plata 2"),
        (3, "Oro 3"),
        (4, "Platino 4"),
        (5, "Diamante 5"),
        (6, "Elite 6")
    ]
    if not ctx.args:
        text = "<u><b>🔐 MENÚ GENERADOR DE CLAVES</b></u>\n\n"
        text += "<b>Planes de uso:</b>\n"
        for i, (max_uses, name) in enumerate(planes, 1):
            text += f"  • <b>{i}</b>: {name} ({max_uses} usos)\n"
        text += "\n<b>Ejemplo:</b> <code>/gen 10 1</code> (Genera 10 claves del plan Bronce 1)"
        await update.effective_chat.send_message(text=text, parse_mode="HTML")
        return

    try:
        num_keys = int(ctx.args[0])
        plan_index = int(ctx.args[1]) - 1
        if not (0 <= plan_index < len(planes)):
            await update.effective_chat.send_message(text="❌ El índice del plan no es válido.")
            return
        max_uses, plan_name = planes[plan_index]
    except (ValueError, IndexError):
        await update.effective_chat.send_message(text="❌ Uso incorrecto. Ejemplo: <code>/gen 10 1</code>", parse_mode="HTML")
        return

    generated_keys = []
    for _ in range(num_keys):
        clave = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        claves[clave] = [plan_name, max_uses]
        generated_keys.append(f"<code>{clave}</code>")

    save_data(DB_KEYS, claves)
    keys_text = "\n".join(generated_keys)
    await update.effective_chat.send_message(
        text=f"<u><b>🔐 Claves generadas ({plan_name})</b></u>\n\n{keys_text}",
        parse_mode="HTML"
    )

@check_super_admin
async def super_pro_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Genera una clave 'SuperPro' que otorga usos ilimitados."""
    claves = load_data(DB_KEYS, {})
    clave = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    claves[clave] = ["SuperPro", float('inf')]
    save_data(DB_KEYS, claves)
    await update.effective_chat.send_message(
        text=f"<u><b>💎 Clave SuperPro generada</b></u>\n\n<code>{clave}</code>",
        parse_mode="HTML"
    )

@check_admin
async def revoke_premium_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso para revocar un plan premium."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_caption(
        caption="<u><b>❌ REVOCAR PLAN PREMIUM</b></u>\n\n"
                "Responde con el ID del usuario al que deseas revocar el plan.\n"
                "Para cancelar, escribe 'cancelar' o usa el botón.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancelar", callback_data="cancel_revoke")]])
    )
    return AWAITING_USER_ID_TO_REVOKE

@check_admin
async def revoke_premium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Revoca el plan premium de un usuario."""
    user_id_to_revoke = update.message.text.strip()
    if user_id_to_revoke.lower() == 'cancelar':
        await update.message.reply_text("❌ Proceso de revocación cancelado.")
        return ConversationHandler.END

    try:
        uid = str(int(user_id_to_revoke))
    except ValueError:
        await update.message.reply_text("❌ ID de usuario no válido. Por favor, ingresa un número. Para cancelar, escribe 'cancelar'.")
        return AWAITING_USER_ID_TO_REVOKE

    users = load_data(DB_USERS, {})
    if uid in users:
        users[uid]["plan_normal"] = {"nombre": "Sin plan", "max": 0, "usados": 0}
        users[uid]["plan_tarjetas"] = {"nombre": "Sin plan", "max": 0, "usados": 0}
        save_data(DB_USERS, users)
        await update.message.reply_text(f"✅ Se ha revocado el plan premium del usuario con ID <code>{uid}</code>.", parse_mode="HTML")
    else:
        await update.message.reply_text(f"❌ No se encontró el usuario con ID <code>{uid}</code>.", parse_mode="HTML")

    return ConversationHandler.END

@check_admin
async def cancel_revoke(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Cancela el proceso de revocación del plan premium."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_caption(
        caption="❌ Proceso de revocación cancelado.",
        parse_mode="HTML",
        reply_markup=KB_RETURN_TO_START
    )
    return ConversationHandler.END

@check_admin
async def ban_user_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso para banear a un usuario."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_caption(
        caption="<u><b>🚫 BANEAR USUARIO</b></u>\n\n"
                "Responde con el ID del usuario que deseas banear.\n"
                "Para cancelar, escribe 'cancelar' o usa el botón.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancelar", callback_data="cancel_ban")]])
    )
    return AWAITING_USER_ID_TO_BAN

@check_admin
async def ban_user_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Banea a un usuario por su ID."""
    user_id_to_ban = update.message.text.strip()
    if user_id_to_ban.lower() == 'cancelar':
        await update.message.reply_text("❌ Proceso de baneo cancelado.")
        return ConversationHandler.END

    try:
        uid_to_ban = int(user_id_to_ban)
    except ValueError:
        await update.message.reply_text("❌ ID de usuario no válido. Por favor, ingresa un número. Para cancelar, escribe 'cancelar'.")
        return AWAITING_USER_ID_TO_BAN

    banned_users = load_data(DB_BANS, default=[])
    if uid_to_ban in banned_users:
        await update.message.reply_text(f"❌ El usuario con ID <code>{uid_to_ban}</code> ya está baneado.", parse_mode="HTML")
    else:
        banned_users.append(uid_to_ban)
        save_data(DB_BANS, banned_users)
        await update.message.reply_text(f"✅ Usuario con ID <code>{uid_to_ban}</code> baneado correctamente.", parse_mode="HTML")

    return ConversationHandler.END

@check_admin
async def unban_user_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso para desbanear a un usuario."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_caption(
        caption="<u><b>✅ DESBANEAR USUARIO</b></u>\n\n"
                "Responde con el ID del usuario que deseas desbanear.\n"
                "Para cancelar, escribe 'cancelar' o usa el botón.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancelar", callback_data="cancel_unban")]])
    )
    return AWAITING_USER_ID_TO_UNBAN

@check_admin
async def unban_user_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Desbanea a un usuario por su ID."""
    user_id_to_unban = update.message.text.strip()
    if user_id_to_unban.lower() == 'cancelar':
        await update.message.reply_text("❌ Proceso de desbaneo cancelado.")
        return ConversationHandler.END

    try:
        uid_to_unban = int(user_id_to_unban)
    except ValueError:
        await update.message.reply_text("❌ ID de usuario no válido. Por favor, ingresa un número. Para cancelar, escribe 'cancelar'.")
        return AWAITING_USER_ID_TO_UNBAN

    banned_users = load_data(DB_BANS, default=[])
    if uid_to_unban in banned_users:
        banned_users.remove(uid_to_unban)
        save_data(DB_BANS, banned_users)
        await update.message.reply_text(f"✅ Usuario con ID <code>{uid_to_unban}</code> desbaneado correctamente.", parse_mode="HTML")
    else:
        await update.message.reply_text(f"❌ El usuario con ID <code>{uid_to_unban}</code> no está baneado.", parse_mode="HTML")

    return ConversationHandler.END

@check_admin
async def cancel_conversation(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Cancela una conversación activa desde un botón."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_caption(
        caption="❌ Proceso cancelado.",
        parse_mode="HTML",
        reply_markup=KB_ADMIN
    )
    return ConversationHandler.END

@check_admin
async def add_stock_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso para subir nuevo stock de cuentas."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_caption(
        caption="<u><b>➕ SUBIR STOCK DE CUENTAS</b></u>\n\n"
                "Responde con el nombre del sitio (ej. `Netflix`, `Spotify`).\n"
                "Para cancelar, escribe 'cancelar' o usa el botón.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancelar", callback_data="cancel_addstock")]])
    )
    return AWAITING_STOCK_SITE

@check_admin
async def add_stock_site(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja la respuesta con el nombre del sitio."""
    sitio = update.message.text.strip()
    if sitio.lower() == 'cancelar':
        await update.message.reply_text("❌ Proceso de subir stock cancelado.")
        return ConversationHandler.END

    ctx.user_data['sitio'] = sitio
    await update.message.reply_text(
        text="Ahora, envía un mensaje de uso que se mostrará junto con las cuentas. Ej: `No cambiar nada, solo usar.`\n"
             "Para cancelar, escribe 'cancelar'.",
        parse_mode="HTML"
    )
    return AWAITING_STOCK_MESSAGE

@check_admin
async def add_stock_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja el mensaje de uso del stock."""
    usage_message = update.message.text.strip()
    if usage_message.lower() == 'cancelar':
        await update.message.reply_text("❌ Proceso de subir stock cancelado.")
        return ConversationHandler.END

    ctx.user_data['usage_message'] = usage_message
    await update.message.reply_text(
        text="Ahora, envía las cuentas en el siguiente formato:\n"
             "`correo:contraseña`\n"
             "o si la cuenta viene con un archivo (foto/video/gif):\n"
             "`correo:contraseña`\n"
             "<i>(envía el archivo en el mismo mensaje)</i>\n"
             "Envía una cuenta por línea.\n"
             "Para cancelar, escribe 'cancelar'.",
        parse_mode="HTML"
    )
    return AWAITING_STOCK_ACCOUNTS

@check_admin
async def add_stock_accounts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja las cuentas enviadas por el admin."""
    if update.message.text and update.message.text.lower() == 'cancelar':
        await update.message.reply_text("❌ Proceso de subir stock cancelado.")
        return ConversationHandler.END

    sitio = ctx.user_data.get('sitio')
    usage_message = ctx.user_data.get('usage_message', "")
    stock = load_data(DB_STOCK, {})
    new_accounts = []

    file_id = None
    file_type = None
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = 'photo'
    elif update.message.video:
        file_id = update.message.video.file_id
        file_type = 'video'
    elif update.message.animation:
        file_id = update.message.animation.file_id
        file_type = 'animation'

    account_text = update.message.caption if update.message.caption else update.message.text
    if not account_text:
        await update.message.reply_text("❌ Por favor, envía las cuentas en el mensaje.")
        return AWAITING_STOCK_ACCOUNTS

    lines = account_text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        new_accounts.append({
            "account": line,
            "file_id": file_id,
            "file_type": file_type
        })

    if sitio not in stock:
        stock[sitio] = {"message": usage_message, "accounts": []}

    # Añade las nuevas cuentas al final de la lista de cuentas existentes.
    existing_accounts = stock[sitio].get("accounts", [])
    stock[sitio]["accounts"] = existing_accounts + new_accounts

    # Asegura que el mensaje de uso se actualice.
    stock[sitio]["message"] = usage_message

    save_data(DB_STOCK, stock)
    num_added = len(new_accounts)
    await update.message.reply_text(f"✅ Se agregaron {num_added} cuentas a `{sitio}`. El stock total ahora es de {len(stock[sitio]['accounts'])} cuentas.", parse_mode="HTML")
    return ConversationHandler.END

@check_admin
async def add_cards_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso para subir nuevo stock de tarjetas."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_caption(
        caption="<u><b>➕ SUBIR STOCK DE TARJETAS</b></u>\n\n"
                "Responde con el nombre del banco o tipo de tarjeta (ej. `Visa`, `MasterCard`).\n"
                "Para cancelar, escribe 'cancelar' o usa el botón.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancelar", callback_data="cancel_addcards")]])
    )
    return AWAITING_CARDS_SITE

@check_admin
async def add_cards_site(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja la respuesta con el nombre del banco o tipo de tarjeta."""
    sitio = update.message.text.strip()
    if sitio.lower() == 'cancelar':
        await update.message.reply_text("❌ Proceso de subir stock de tarjetas cancelado.")
        return ConversationHandler.END

    ctx.user_data['sitio_cards'] = sitio
    await update.message.reply_text(
        text="Ahora, envía un mensaje de uso que se mostrará junto con las tarjetas. Ej: `No cambiar nada, solo usar.`\n"
             "Para cancelar, escribe 'cancelar'.",
        parse_mode="HTML"
    )
    return AWAITING_CARDS_MESSAGE

@check_admin
async def add_cards_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja el mensaje de uso del stock de tarjetas."""
    usage_message = update.message.text.strip()
    if usage_message.lower() == 'cancelar':
        await update.message.reply_text("❌ Proceso de subir stock de tarjetas cancelado.")
        return ConversationHandler.END

    ctx.user_data['usage_message_cards'] = usage_message
    await update.message.reply_text(
        text="Ahora, envía las tarjetas en el siguiente formato:\n"
             "`tarjeta|mes|año|cvv`\n"
             "o si la tarjeta viene con un archivo (foto/video/gif):\n"
             "`tarjeta|mes|año|cvv`\n"
             "<i>(envía el archivo en el mismo mensaje)</i>\n"
             "Envía una tarjeta por línea.\n"
             "Para cancelar, escribe 'cancelar'.",
        parse_mode="HTML"
    )
    return AWAITING_CARDS_ACCOUNTS

@check_admin
async def add_cards_accounts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja las tarjetas enviadas por el admin."""
    if update.message.text and update.message.text.lower() == 'cancelar':
        await update.message.reply_text("❌ Proceso de subir stock de tarjetas cancelado.")
        return ConversationHandler.END

    sitio = ctx.user_data.get('sitio_cards')
    usage_message = ctx.user_data.get('usage_message_cards', "")
    cards_db = load_data(DB_CARDS, {})
    new_cards = []

    file_id = None
    file_type = None
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = 'photo'
    elif update.message.video:
        file_id = update.message.video.file_id
        file_type = 'video'
    elif update.message.animation:
        file_id = update.message.animation.file_id
        file_type = 'animation'

    card_text = update.message.caption if update.message.caption else update.message.text
    if not card_text:
        await update.message.reply_text("❌ Por favor, envía las tarjetas en el mensaje.")
        return AWAITING_CARDS_ACCOUNTS

    lines = card_text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        new_cards.append({
            "card": line,
            "file_id": file_id,
            "file_type": file_type
        })

    if sitio not in cards_db:
        cards_db[sitio] = {"message": usage_message, "cards": []}

    # Añade las nuevas tarjetas al final de la lista de tarjetas existentes.
    existing_cards = cards_db[sitio].get("cards", [])
    cards_db[sitio]["cards"] = existing_cards + new_cards

    # Asegura que el mensaje de uso se actualice.
    cards_db[sitio]["message"] = usage_message

    save_data(DB_CARDS, cards_db)
    num_added = len(new_cards)
    await update.message.reply_text(f"✅ Se agregaron {num_added} tarjetas a `{sitio}`. El stock total ahora es de {len(cards_db[sitio]['cards'])} tarjetas.", parse_mode="HTML")
    return ConversationHandler.END

@check_admin
async def gen_cards_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando para generar claves de tarjetas."""
    card_keys = load_data(DB_CARD_KEYS, {})
    planes = [
        (1, "Bronze Card 1"),
        (2, "Silver Card 2"),
        (3, "Gold Card 3"),
        (4, "Platinum Card 4"),
        (5, "Diamond Card 5"),
        (6, "Elite Card 6")
    ]
    if not ctx.args:
        text = "<u><b>💳 MENÚ GENERADOR DE CLAVES DE TARJETAS</b></u>\n\n"
        text += "<b>Planes de uso:</b>\n"
        for i, (max_uses, name) in enumerate(planes, 1):
            text += f"  • <b>{i}</b>: {name} ({max_uses} usos)\n"
        text += "\n<b>Ejemplo:</b> <code>/gen_cards_key 10 1</code> (Genera 10 claves del plan Bronze Card 1)"
        await update.effective_chat.send_message(text=text, parse_mode="HTML")
        return

    try:
        num_keys = int(ctx.args[0])
        plan_index = int(ctx.args[1]) - 1
        if not (0 <= plan_index < len(planes)):
            await update.effective_chat.send_message(text="❌ El índice del plan no es válido.")
            return
        max_uses, plan_name = planes[plan_index]
    except (ValueError, IndexError):
        await update.effective_chat.send_message(text="❌ Uso incorrecto. Ejemplo: <code>/gen_cards_key 10 1</code>", parse_mode="HTML")
        return

    generated_keys = []
    for _ in range(num_keys):
        clave = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        card_keys[clave] = [plan_name, max_uses]
        generated_keys.append(f"<code>{clave}</code>")

    save_data(DB_CARD_KEYS, card_keys)
    keys_text = "\n".join(generated_keys)
    await update.effective_chat.send_message(
        text=f"<u><b>💳 Claves de tarjetas generadas ({plan_name})</b></u>\n\n{keys_text}",
        parse_mode="HTML"
    )

@check_admin
async def send_broadcast_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de envío de un anuncio masivo."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_caption(
        caption="<u><b>📢 ENVIAR ANUNCIO</b></u>\n\n"
                "Responde con el mensaje que deseas enviar a todos los usuarios. Puedes usar formato HTML.\n"
                "Para cancelar, escribe 'cancelar'.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancelar", callback_data="cancel_broadcast")]])
    )
    return BROADCAST_CONTENT

@check_admin
async def send_broadcast_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maneja el contenido del anuncio y lo envía a todos los usuarios."""
    message_content = update.message.text
    if message_content and message_content.lower() == 'cancelar':
        await update.message.reply_text("❌ Envío de anuncio masivo cancelado.")
        return ConversationHandler.END

    users = load_data(DB_USERS, {})
    sent_count = 0
    failed_count = 0
    for user_id in users.keys():
        try:
            await ctx.bot.send_message(
                chat_id=user_id,
                text=message_content,
                parse_mode="HTML"
            )
            sent_count += 1
        except error.TelegramError as e:
            logging.error(f"Error al enviar mensaje a {user_id}: {e}")
            failed_count += 1

    await update.message.reply_text(
        f"✅ Anuncio enviado a {sent_count} usuarios.\n"
        f"❌ Falló para {failed_count} usuarios.",
        parse_mode="HTML"
    )
    return ConversationHandler.END

@check_admin
async def add_admin_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso para agregar un nuevo administrador."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_caption(
        caption="<u><b>👑 PROMOVER A ADMIN</b></u>\n\n"
                "Responde con el ID del usuario que deseas promover.\n"
                "Para cancelar, escribe 'cancelar' o usa el botón.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancelar", callback_data="cancel_add_admin")]])
    )
    return AWAITING_ADMIN_ID

@check_admin
async def add_admin_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Agrega un nuevo administrador por su ID."""
    user_id_to_add = update.message.text.strip()
    if user_id_to_add.lower() == 'cancelar':
        await update.message.reply_text("❌ Proceso de promoción cancelado.")
        return ConversationHandler.END

    try:
        uid_to_add = int(user_id_to_add)
    except ValueError:
        await update.message.reply_text("❌ ID de usuario no válido. Por favor, ingresa un número. Para cancelar, escribe 'cancelar'.")
        return AWAITING_ADMIN_ID

    admins = load_data(DB_ADMINS, default=[])
    if uid_to_add in admins:
        await update.message.reply_text(f"❌ El usuario con ID <code>{uid_to_add}</code> ya es administrador.", parse_mode="HTML")
    else:
        admins.append(uid_to_add)
        save_data(DB_ADMINS, admins)
        await update.message.reply_text(f"✅ Usuario con ID <code>{uid_to_add}</code> promovido a administrador correctamente.", parse_mode="HTML")

    return ConversationHandler.END

@check_admin
async def remove_admin_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso para remover un administrador."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_caption(
        caption="<u><b>💀 DEGRADAR ADMIN</b></u>\n\n"
                "Responde con el ID del usuario que deseas degradar.\n"
                "Para cancelar, escribe 'cancelar' o usa el botón.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancelar", callback_data="cancel_remove_admin")]])
    )
    return AWAITING_REMOVE_ADMIN_ID

@check_admin
async def remove_admin_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Remueve un administrador por su ID."""
    user_id_to_remove = update.message.text.strip()
    if user_id_to_remove.lower() == 'cancelar':
        await update.message.reply_text("❌ Proceso de degradación cancelado.")
        return ConversationHandler.END

    try:
        uid_to_remove = int(user_id_to_remove)
    except ValueError:
        await update.message.reply_text("❌ ID de usuario no válido. Por favor, ingresa un número. Para cancelar, escribe 'cancelar'.")
        return AWAITING_REMOVE_ADMIN_ID

    if uid_to_remove == ADMIN:
        await update.message.reply_text("❌ No puedes degradar al super-administrador del bot.", parse_mode="HTML")
        return ConversationHandler.END

    admins = load_data(DB_ADMINS, default=[])
    if uid_to_remove in admins:
        admins.remove(uid_to_remove)
        save_data(DB_ADMINS, admins)
        await update.message.reply_text(f"✅ Usuario con ID <code>{uid_to_remove}</code> degradado correctamente.", parse_mode="HTML")
    else:
        await update.message.reply_text(f"❌ El usuario con ID <code>{uid_to_remove}</code> no es administrador.", parse_mode="HTML")

    return ConversationHandler.END

@check_admin
async def show_users(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Muestra el número de usuarios y administradores."""
    query = update.callback_query
    await query.answer()

    users = load_data(DB_USERS, {})
    admins = load_data(DB_ADMINS, [])
    banned_users = load_data(DB_BANS, [])

    num_users = len(users)
    num_admins = len(admins)
    num_banned = len(banned_users)

    admin_list = "\n".join([f"• <code>{aid}</code>" for aid in admins]) if admins else "No hay otros administradores."

    info_text = (
        f"<u><b>👥 ESTADÍSTICAS DE USUARIOS</b></u>\n\n"
        f"<b>• Total de usuarios:</b> {num_users}\n"
        f"<b>• Total de administradores:</b> {num_admins + 1}\n" # +1 para el super-admin
        f"<b>• Usuarios baneados:</b> {num_banned}\n\n"
        f"<b>Otros administradores:</b>\n"
        f"{admin_list}"
    )

    await query.edit_message_caption(
        caption=info_text,
        parse_mode="HTML",
        reply_markup=KB_RETURN_TO_START
    )

def main() -> None:
    """Función principal para iniciar el bot."""
    application = Application.builder().token(TOKEN).build()

    # Handlers para comandos normales
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("key", key_cmd))
    application.add_handler(CommandHandler("get", get_cmd))

    # Handlers para callbacks de botones
    application.add_handler(CallbackQueryHandler(show_profile, pattern="^profile$"))
    application.add_handler(CallbackQueryHandler(show_stock_menu, pattern="^stock$"))
    application.add_handler(CallbackQueryHandler(show_cuentas_stock, pattern="^show_stock_cuentas$"))
    application.add_handler(CallbackQueryHandler(show_cards_stock, pattern="^show_stock_tarjetas$"))
    application.add_handler(CallbackQueryHandler(show_cmds, pattern="^cmds$"))
    application.add_handler(CallbackQueryHandler(return_to_start, pattern="^start_menu$"))

    # Handlers para el panel de administración
    application.add_handler(CallbackQueryHandler(show_admin_panel, pattern="^panel$"))
    application.add_handler(CallbackQueryHandler(gen_cmd, pattern="^gen_cmd$"))
    application.add_handler(CommandHandler("gen", gen_cmd))
    application.add_handler(CallbackQueryHandler(super_pro_key, pattern="^super_pro_key$"))
    application.add_handler(CommandHandler("super_pro_key", super_pro_key))
    application.add_handler(CallbackQueryHandler(add_admin_start, pattern="^add_admin_start$"))
    application.add_handler(CallbackQueryHandler(remove_admin_start, pattern="^rem_admin_start$"))
    application.add_handler(CallbackQueryHandler(show_users, pattern="^users_cmd$"))
    application.add_handler(CallbackQueryHandler(gen_cards_key, pattern="^gen_cards_key$"))
    application.add_handler(CommandHandler("gen_cards_key", gen_cards_key))

    # ConversationHandlers para procesos de varios pasos
    conv_revoke = ConversationHandler(
        entry_points=[CallbackQueryHandler(revoke_premium_start, pattern="^revoke_premium_start$")],
        states={
            AWAITING_USER_ID_TO_REVOKE: [MessageHandler(filters.TEXT & ~filters.COMMAND, revoke_premium)],
        },
        fallbacks=[CallbackQueryHandler(cancel_revoke, pattern="^cancel_revoke$")]
    )
    application.add_handler(conv_revoke)

    conv_ban = ConversationHandler(
        entry_points=[CallbackQueryHandler(ban_user_start, pattern="^ban_user_start$")],
        states={
            AWAITING_USER_ID_TO_BAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, ban_user_id)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conversation, pattern="^cancel_ban$")]
    )
    application.add_handler(conv_ban)

    conv_unban = ConversationHandler(
        entry_points=[CallbackQueryHandler(unban_user_start, pattern="^unban_user_start$")],
        states={
            AWAITING_USER_ID_TO_UNBAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, unban_user_id)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conversation, pattern="^cancel_unban$")]
    )
    application.add_handler(conv_unban)

    conv_add_stock = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_stock_start, pattern="^addstock_start$")],
        states={
            AWAITING_STOCK_SITE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_stock_site)],
            AWAITING_STOCK_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_stock_message)],
            AWAITING_STOCK_ACCOUNTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_stock_accounts),
                MessageHandler(filters.PHOTO & ~filters.COMMAND, add_stock_accounts),
                MessageHandler(filters.VIDEO & ~filters.COMMAND, add_stock_accounts),
                MessageHandler(filters.ANIMATION & ~filters.COMMAND, add_stock_accounts),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_conversation, pattern="^cancel_addstock$")]
    )
    application.add_handler(conv_add_stock)

    conv_add_cards = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_cards_start, pattern="^addcards_start$")],
        states={
            AWAITING_CARDS_SITE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_cards_site)],
            AWAITING_CARDS_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_cards_message)],
            AWAITING_CARDS_ACCOUNTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_cards_accounts),
                MessageHandler(filters.PHOTO & ~filters.COMMAND, add_cards_accounts),
                MessageHandler(filters.VIDEO & ~filters.COMMAND, add_cards_accounts),
                MessageHandler(filters.ANIMATION & ~filters.COMMAND, add_cards_accounts),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_conversation, pattern="^cancel_addcards$")]
    )
    application.add_handler(conv_add_cards)

    conv_broadcast = ConversationHandler(
        entry_points=[CallbackQueryHandler(send_broadcast_start, pattern="^send_msg_cmd$")],
        states={
            BROADCAST_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_broadcast_message)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conversation, pattern="^cancel_broadcast$")]
    )
    application.add_handler(conv_broadcast)

    conv_add_admin = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_admin_start, pattern="^add_admin_start$")],
        states={
            AWAITING_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_id)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conversation, pattern="^cancel_add_admin$")]
    )
    application.add_handler(conv_add_admin)

    conv_remove_admin = ConversationHandler(
        entry_points=[CallbackQueryHandler(remove_admin_start, pattern="^rem_admin_start$")],
        states={
            AWAITING_REMOVE_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_admin_id)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conversation, pattern="^cancel_remove_admin$")]
    )
    application.add_handler(conv_remove_admin)

# Handler para mensajes que no son comandos (debe ir al final)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown_messages))
    
# Handler para mensajes que no son comandos (debe ir al final)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown_messages))

    logging.info("PAUBLITE_GT Bot iniciado.")
    application.run_polling()

if __name__ == "__main__":
    main()
