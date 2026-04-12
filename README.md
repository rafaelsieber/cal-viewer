# Cal Viewer

Visualizador e editor de compromissos de calendário ICS para GNOME, feito com Python + GTK4/Libadwaita.

## Funcionalidades

- Exibe os compromissos do dia atual de um arquivo `.ics`
- Navega entre dias com os botões `←` / `→` ou teclas de seta do teclado
- Clique na data para abrir um calendário e saltar para qualquer dia
- Botão **Hoje** para voltar rapidamente ao dia atual
- **Criar eventos** diretamente pelo app (título, data, horário, local, descrição, recorrência, dia todo)
- **Editar eventos** clicando sobre eles na lista
- **Deletar eventos** com suporte a recorrências (remover ocorrência única via EXDATE ou apagar tudo)
- Tela vazia com botão de atalho para adicionar compromisso
- Botão de **atualização manual** para recarregar o ICS do disco
- Recarregamento automático do ICS a cada troca de dia (captura eventos criados externamente)
- Seleção do arquivo `.ics` via diálogo nativo (suporta pastas montadas via GVFS/SFTP)
- Salva automaticamente o caminho do arquivo nas configurações (`~/.config/cal-viewer/config.json`)
- Parser ICS nativo (sem dependências externas além de stdlib + GTK)
- Suporte a eventos recorrentes: RRULE diário, semanal, mensal e anual
- Suporte a exceções de recorrência (EXDATE)
- Suporte a TZID, UTC e floating datetimes
- Integração com o lançador do GNOME (arquivo `.desktop` + ícone SVG)

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
git clone https://github.com/rafaelsieber/cal-viewer.git
cd cal-viewer
chmod +x install.sh
./install.sh
```

O `install.sh` cria um virtualenv em `~/.local/share/cal-viewer/venv/` e usa um **symlink** para o diretório `src/` do projeto — assim, basta `git pull` para atualizar o app sem reinstalar.

## Desinstalação

```bash
./uninstall.sh
```

## Uso

Após instalar, execute `cal-viewer` no terminal ou busque **Cal Viewer** no lançador do GNOME.

Na primeira execução, clique no botão de abrir arquivo (ícone de pasta) e selecione o arquivo `.ics`. O caminho é salvo automaticamente para as próximas execuções.

### Atalhos de teclado

| Tecla   | Ação         |
|---------|--------------|
| `←`     | Dia anterior |
| `→`     | Próximo dia  |
| `Home`  | Hoje         |

## Estrutura do projeto

```
cal-viewer/
├── src/
│   └── cal_viewer.py    # Aplicação principal (parser ICS, UI GTK4/Adw)
├── icons/
│   └── cal-viewer.svg   # Ícone da aplicação
├── data/
│   └── cal-viewer.desktop
├── requirements.txt
├── install.sh
├── uninstall.sh
└── README.md
```

## Licença

GPL-3.0-or-later
