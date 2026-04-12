# Cal Viewer

Visualizador simples de compromissos de calendário ICS para GNOME, feito com Python + GTK4/Libadwaita.

## Funcionalidades

- Exibe os compromissos do dia atual de um arquivo `.ics`
- Navega entre dias com os botões `←` / `→` ou teclas de seta do teclado
- Botão **Hoje** para voltar rapidamente ao dia atual
- Seleção do arquivo `.ics` via diálogo nativo (suporta pastas montadas no GNOME)
- Salva automaticamente o caminho do arquivo nas configurações do usuário (`~/.config/cal-viewer/config.json`)
- Suporte a eventos recorrentes (RRULE: diário, semanal, mensal, anual)
- Suporte a exceções de recorrência (EXDATE)
- Exibe horário, local e descrição dos eventos
- Integração com o lançador de aplicativos do GNOME (arquivo `.desktop` + ícone)

## Requisitos

- Python 3.10+
- GTK 4 + Libadwaita (`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`)
- `python3-venv`

No Fedora/RHEL:
```bash
sudo dnf install python3-gobject gtk4 libadwaita python3-venv
```

No Ubuntu/Debian:
```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 python3-venv
```

## Instalação

```bash
git clone https://github.com/rafaelortiz/cal-viewer.git
cd cal-viewer
chmod +x install.sh
./install.sh
```

## Desinstalação

```bash
./uninstall.sh
```

## Uso

Após instalar, execute `cal-viewer` no terminal ou busque **Cal Viewer** no lançador do GNOME.

Na primeira execução, clique no botão de abrir arquivo (ícone de pasta) e selecione o arquivo `.ics` desejado. O caminho é salvo automaticamente para as próximas execuções.

### Atalhos de teclado

| Tecla       | Ação             |
|-------------|------------------|
| `←`         | Dia anterior     |
| `→`         | Próximo dia      |
| `Home`      | Hoje             |

## Estrutura do projeto

```
cal-viewer/
├── src/
│   └── cal_viewer.py   # Aplicação principal
├── icons/
│   └── cal-viewer.svg  # Ícone da aplicação
├── data/
│   └── cal-viewer.desktop
├── requirements.txt
├── install.sh
├── uninstall.sh
└── README.md
```

## Licença

GPL-3.0-or-later
