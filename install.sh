#!/usr/bin/env bash
# Cal Viewer - Install script
# Creates a venv, installs dependencies and registers the app in GNOME.

set -euo pipefail

APP_NAME="cal-viewer"
INSTALL_DIR="$HOME/.local/share/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICONS_DIR="$HOME/.local/share/icons/hicolor"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Instalando Cal Viewer..."

# ── 1. Cria diretório de instalação ──────────────────────────────────────────
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$DESKTOP_DIR"

# ── 2. Symlink do src (git pull atualiza automaticamente) ─────────────────────
echo "    Linkando arquivos..."
ln -sfn "$SCRIPT_DIR/src"              "$INSTALL_DIR/src"
ln -sfn "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"

# ── 3. Cria o virtualenv ─────────────────────────────────────────────────────
echo "    Criando ambiente virtual Python..."
python3 -m venv "$INSTALL_DIR/venv" --system-site-packages

# ── 4. Instala dependências ──────────────────────────────────────────────────
echo "    Instalando dependências..."
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

# ── 5. Instala ícone SVG ─────────────────────────────────────────────────────
echo "    Instalando ícone..."
mkdir -p "$ICONS_DIR/scalable/apps"
cp "$SCRIPT_DIR/icons/cal-viewer.svg" "$ICONS_DIR/scalable/apps/cal-viewer.svg"

# Também gera PNGs de 48 e 256 px se o rsvg-convert estiver disponível
for SIZE in 48 128 256; do
    mkdir -p "$ICONS_DIR/${SIZE}x${SIZE}/apps"
    if command -v rsvg-convert &>/dev/null; then
        rsvg-convert -w $SIZE -h $SIZE \
            "$SCRIPT_DIR/icons/cal-viewer.svg" \
            -o "$ICONS_DIR/${SIZE}x${SIZE}/apps/cal-viewer.png" 2>/dev/null || true
    elif command -v convert &>/dev/null; then
        convert -background none \
            -resize "${SIZE}x${SIZE}" \
            "$SCRIPT_DIR/icons/cal-viewer.svg" \
            "$ICONS_DIR/${SIZE}x${SIZE}/apps/cal-viewer.png" 2>/dev/null || true
    fi
done

# ── 6. Cria o wrapper executável ─────────────────────────────────────────────
echo "    Criando executável em $BIN_DIR/$APP_NAME..."
cat > "$BIN_DIR/$APP_NAME" <<EOF
#!/usr/bin/env bash
exec "$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/src/cal_viewer.py" "\$@"
EOF
chmod +x "$BIN_DIR/$APP_NAME"

# ── 7. Instala o arquivo .desktop (com caminho absoluto no Exec) ─────────────
echo "    Registrando entrada no menu..."
sed "s|^Exec=cal-viewer|Exec=$BIN_DIR/$APP_NAME|" \
    "$SCRIPT_DIR/data/cal-viewer.desktop" > "$DESKTOP_DIR/cal-viewer.desktop"

# Atualiza caches do sistema de ícones e menus
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
echo "✓  Cal Viewer instalado com sucesso!"
echo "   Execute:  cal-viewer"
echo "   Ou busque 'Cal Viewer' no lançador de aplicativos do GNOME."
echo "   Atualizações: git pull  (sem precisar reinstalar)"

# Avisa se ~/.local/bin não estiver no PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "AVISO: $BIN_DIR não está no seu PATH."
    echo "       Adicione ao seu ~/.bashrc ou ~/.profile:"
    echo "       export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
