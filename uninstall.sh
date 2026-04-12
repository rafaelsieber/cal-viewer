#!/usr/bin/env bash
# Cal Viewer - Uninstall script

set -euo pipefail

APP_NAME="cal-viewer"
INSTALL_DIR="$HOME/.local/share/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICONS_DIR="$HOME/.local/share/icons/hicolor"
CONFIG_DIR="$HOME/.config/cal-viewer"

echo "==> Desinstalando Cal Viewer..."

# ── Remove executável ─────────────────────────────────────────────────────────
if [ -f "$BIN_DIR/$APP_NAME" ]; then
    rm -f "$BIN_DIR/$APP_NAME"
    echo "    Executável removido."
fi

# ── Remove arquivos da aplicação ──────────────────────────────────────────────
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo "    Arquivos do app removidos."
fi

# ── Remove entrada .desktop ───────────────────────────────────────────────────
if [ -f "$DESKTOP_DIR/$APP_NAME.desktop" ]; then
    rm -f "$DESKTOP_DIR/$APP_NAME.desktop"
    echo "    Entrada do menu removida."
fi

# ── Remove ícones ─────────────────────────────────────────────────────────────
for SIZE in scalable 48x48 128x128 256x256; do
    icon_svg="$ICONS_DIR/$SIZE/apps/$APP_NAME.svg"
    icon_png="$ICONS_DIR/$SIZE/apps/$APP_NAME.png"
    [ -f "$icon_svg" ] && rm -f "$icon_svg"
    [ -f "$icon_png" ] && rm -f "$icon_png"
done
echo "    Ícones removidos."

# ── Pergunta sobre configuração ───────────────────────────────────────────────
if [ -d "$CONFIG_DIR" ]; then
    read -rp "    Remover configurações e caminho do ICS salvo? [s/N] " ans
    case "$ans" in
        [sS]|[yY])
            rm -rf "$CONFIG_DIR"
            echo "    Configurações removidas."
            ;;
        *)
            echo "    Configurações mantidas em $CONFIG_DIR"
            ;;
    esac
fi

# ── Atualiza caches ────────────────────────────────────────────────────────────
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -qtf "$ICONS_DIR" 2>/dev/null || true
fi
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database -q "$DESKTOP_DIR" 2>/dev/null || true
fi
if command -v xdg-desktop-menu &>/dev/null; then
    xdg-desktop-menu forceupdate 2>/dev/null || true
fi

echo ""
echo "✓  Cal Viewer desinstalado com sucesso."
