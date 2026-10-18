A multi-video wall player for the desktop, built on libmpv and PySide6.

Play multiple videos, GIFs and images at once in a single window.

## Contents

- [Compatibility](#compatibility)
- [Installation](#installation) (Linux, Windows)
- [Usage](#usage) (mouse, keyboard, toolbar reference, saved settings)
- [Performance tips](#performance-tips)
- [Troubleshooting](#troubleshooting)

## Compatibility

| System | Status |
| --- | --- |
| Arch-based Linux (Arch, CachyOS, Manjaro, EndeavourOS) with KDE Plasma 6 on Wayland (through XWayland) | Tested |
| Other Linux distributions on X11 or Wayland (through XWayland) | Expected to work, not tested |
| Windows 10 / 11 (64-bit) | Tested |
| macOS | Not supported (embedding mpv into Qt windows is unreliable there) |
| Alpine and other musl-based Linux | Not supported (PySide6 has no wheels for musl) |

"Not tested" just means I haven't tested it on my computer, because I am lazy, so there's no 
confirmation on whether or not it works on that platform. Please open an issue with your results if you do test it.

## Installation

You need Python 3.10 or newer, libmpv, and two Python packages (PySide6 and python-mpv).

### Step 1: Get the code

```bash
git clone https://github.com/Hayarare/mosaic-wall
cd mosaic-wall
```

Or download `mosaic_wall.py` and `requirements.txt` into a folder by downloading the zip with the green Code button.

### Step 2: Install libmpv and system libraries

Follow the section for your system: [Linux](#linux) or [Windows](#windows).

#### Linux

Install libmpv and the Qt xcb cursor library. Find the distro you're using below.

| Distributions | Command |
| --- | --- |
| **Arch, CachyOS, Manjaro, EndeavourOS** | `sudo pacman -S mpv python xcb-util-cursor` |
| **Debian 12+, Ubuntu 24.04+, Linux Mint 22+, Pop!_OS** | `sudo apt install libmpv2 python3-venv python3-pip libxcb-cursor0` |
| **Ubuntu 22.04 and Linux Mint 21** | `sudo apt install libmpv1 python3-venv python3-pip libxcb-cursor0` |
| **Fedora** (needs [RPM Fusion](https://rpmfusion.org/Configuration)) | see the Fedora notes below |
| **openSUSE Tumbleweed / Leap** | `sudo zypper install libmpv2 python3 libxcb-cursor0` |
| **Gentoo** | `echo "media-video/mpv libmpv" >> /etc/portage/package.use/mpv`, then `emerge media-video/mpv` |

> Package names for openSUSE and Gentoo are from memory and may differ between releases. If one is not
> found, search your package manager for "mpv" and install the package that provides `libmpv.so.2`.

**Fedora notes:** Fedora's own repositories do not ship mpv's library because of codec licensing, so
enable RPM Fusion Free first, then install:

```bash
sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm
sudo dnf install mpv-libs python3 xcb-util-cursor
```

**Check that libmpv is installed:** This should print a line containing `libmpv.so.2`:

```bash
ldconfig -p | grep libmpv
```

On Arch, the `mpv` package already includes libmpv, so there is nothing else to install.

**Minimal or server installs (Debian/Ubuntu):** If Qt later complains about missing xcb libraries, also install:

```bash
sudo apt install libegl1 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-shape0
```

**Which desktops work:** The app embeds mpv into Qt windows through X11, so on Wayland it runs through XWayland.

| Desktop | Notes |
| --- | --- |
| KDE Plasma (X11 or Wayland) | Tested on Plasma 6 (Wayland). XWayland is installed by default |
| GNOME, Cinnamon, MATE, Xfce, LXQt | Expected to work. XWayland is installed by default on Wayland sessions |
| Tiling window managers (i3, sway, Hyprland, bspwm) | Needs XWayland running (sway and Hyprland have it on by default). The app uses two helper windows (an invisible mouse overlay and the fullscreen exit button), so set a floating rule for this app's windows or the window manager will try to tile them |

#### Windows

1. **Install Python.** Download the 64-bit installer from [python.org](https://www.python.org/downloads/)
   (3.10 to 3.13) and tick **Add python.exe to PATH** on the first screen.
2. **Download libmpv.** Go to [github.com/shinchiro/mpv-winbuild-cmake/releases](https://github.com/shinchiro/mpv-winbuild-cmake/releases)
   and download the file whose name starts with `mpv-dev-x86_64-` and ends in `.7z`.
   If you are unsure about your CPU, pick the one without `-v3` in the name (the `v3` builds need a newer
   CPU with AVX2).
3. **Extract it.** Use your archive extractor (Nanazip(https://nanazip.org/) is recommended) to open the zip file and extract.
4. **Copy the DLL.** Copy `libmpv-2.dll` (some builds call it `mpv-2.dll`) into the same folder as
   `mosaic_wall.py`. Python and the DLL must both be 64-bit.

Your folder should look like this:

```text
mosaic-wall\
  mosaic_wall.py
  requirements.txt
  libmpv-2.dll
```

### Step 3: Create a virtual environment

Modern Linux distributions block `pip install` outside a virtual environment, so make one. It also
keeps the project's packages separate on Windows.

**Linux (bash or zsh)**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Linux with fish shell** (fish cannot read the `activate` script, because it's stupid)

```fish
python3 -m venv venv
source venv/bin/activate.fish
```

**Windows (PowerShell)**

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

If PowerShell says scripts are disabled, run this once and try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**Windows (Command Prompt)**

```bat
python -m venv venv
venv\Scripts\activate.bat
```

Your prompt should now start with `(venv)`.

> **Tip:** if the project folder is on an NTFS or exFAT drive (for example a mounted Windows data
> drive on Linux), create the venv in your home folder instead, such as `python3 -m venv ~/.venvs/mosaic`.
> Those filesystems cannot hold a venv.

### Step 4: Install the Python packages

```bash
pip install -r requirements.txt
```

### Step 5: Run it

**Linux / Windows**

```bash
python mosaic_wall.py
```


Put paths with spaces in quotes. Use `pythonw mosaic_wall.py` on Windows to run without a console window.

Next time, activate the venv again (Step 3) and run the same command.

## Usage

### Mouse

| Action | What it does |
| --- | --- |
| Drag a tile onto another tile | Swaps the two tiles |
| Double-click a tile | Focus view (click again to go back) |
| Right-click a tile | Tile menu: open a file, pick from library, audio, A-B loop, speed, fit/crop, remove |
| Drop files from your file manager onto a tile | Plays the first file in that tile and adds the rest to the library |

### Keyboard

| Key | Action |
| --- | --- |
| `Space` | Pause / play all |
| `M` | Mute / unmute |
| `N` | Next clip in every tile |
| `R` | Random seek in every tile |
| `F` | Fullscreen |
| `Esc` | Leave fullscreen |

In fullscreen there is also an "Exit fullscreen" button in the top-right corner.

### Toolbar

The toolbar runs along the top of the window and is hidden in fullscreen. The "library" is the list of
files you added. Tiles take their files from it one after another, and start again from the beginning
when it runs out, so a small library can still fill a large wall.

| Control | Default | What it does |
| --- | --- | --- |
| **Add files** | | Opens a file picker. The new files join the library and fill any empty tiles |
| **Add folder** | | Adds every supported file in the folder and all its subfolders |
| **Clear** | | Empties the library and stops every tile (they turn black). Your files are not deleted and your saved crop settings are kept |
| **Tiles** | 4 | Number of tiles, from 1 to 200. Typing a number applies when you press Enter or click away; the arrows apply at once. Lowering the number removes tiles from the end. Raising it adds tiles two at a time so the window stays responsive |
| **Image secs** | 5 | How many seconds each still image stays on screen, from 1 to 300. The infinity symbol (0) shows images until you change them. Only used in the two "next" modes; in "Loop each clip" an image stays on screen |
| **Pause/Play** | playing | Pauses or resumes every tile. Same as `Space` |
| **Muted** | on | Mutes every tile. All tiles start muted. Use "Solo audio" in a tile's right-click menu, or focus view, to hear a single tile |
| **Vol** | 70 | Volume slider (0 to 100) for all tiles.|
| **Shuffle** | on | Shuffles the order in which tiles pull files from the library. Turning it off takes effect the next time the library wraps around |
| **Next clips** | | Gives every tile the next file from the library. |
| **Random seek** | | Jumps every video to a random point. |
| **Fullscreen** | | Hides the toolbar and status bar and fills the screen. |

**Layout options**

| Option | Result |
| --- | --- |
| Auto mosaic | Chooses rows or columns so every tile matches its clip's shape as closely as possible, and the tiles always fill the whole window. |
| Single row | All tiles side by side in one row |
| Single column | All tiles stacked in one column |
| Hero (1 big + rest) | The first tile is large (35% to 65% of the window width, depending on its shape) and the rest are packed into the remaining space. The "first" tile is the top-left one, so drag any tile there to make it the hero |

**Default fit options**

| Option | Result |
| --- | --- |
| Fill (crop) | The clip covers the whole tile and the edges are cropped. No black bars |
| Fit (black bars) | The whole frame is shown, with black bars where the shapes differ |
| Stretch | The clip is stretched to the tile shape. |

**Mode options**

| Option | Result |
| --- | --- |
| Loop each clip | Each tile repeats its clip forever |
| Play next when finished | When a clip ends, the tile takes the next file from the library |
| Random start, then next | Same as above, but each video starts at a random point (up to 80% in). Applies to videos longer than 10 seconds |

### Per-file fit and crop

Right-click a tile and open **Fit / crop (this file)** to override the default for that one file:

- **Use default / Fill (crop) / Fit (black bars) / Stretch**
- **Crop position**: Center, Left, Right, Top or Bottom, which chooses the part of the clip that stays visible when cropping
- **Zoom in / Zoom out**
- **Reset this file's view**

### Where settings are saved

Per-file fit/crop settings are saved automatically in a JSON file in your home folder:

| System | Location |
| --- | --- |
| Linux | `~/.config/mosaic_wall/views.json` (this path is used even if you set `XDG_CONFIG_HOME`) |
| Windows | `C:\Users\<your name>\.config\mosaic_wall\views.json` (also written as `%USERPROFILE%\.config\mosaic_wall\views.json`) |

Settings are stored against the file's full path, so moving or renaming a file starts it from the
default again. To reset every file, close the app and delete `views.json`. The toolbar settings
(tiles, layout, mode and so on) are not saved and return to their defaults each time you start the app.

### Supported files

| Type | Extensions |
| --- | --- |
| Video | mp4, mkv, avi, mov, webm, m4v, wmv, flv, ts, mpg, mpeg, gif, 3gp, ogv, m2ts |
| Image | jpg, jpeg, png, webp, bmp, tif, tiff, avif, jxl |

Anything your libmpv build can decode will play if you add its extension to `VIDEO_EXT` or
`IMAGE_EXT` near the top of `mosaic_wall.py`.


## Performance tips

Every tile is a full video decoder, so the number of tiles you can run depends on your hardware.

- **Use lower resolution videos on big walls** A tile in a 4x3 grid is only about 480x270 pixels on a 1080p screen.
  Low-resolution H.264 copies also run far more tiles than full-size originals.
- **For older graphics cards** Most GPUs older than NVIDIA RTX 30, AMD RDNA 2 and Intel Arc cannot
  decode AV1, so the CPU does the work. Convert to H.264 or HEVC if you need many tiles (see below).
- **Decoder threads per tile** are set with `MOSAIC_THREADS`. Above 16 tiles the app uses 1 thread per tile by default.
- **Hardware decoder** is chosen with `MOSAIC_HWDEC` (default `auto-safe`).

| `MOSAIC_HWDEC` value | Use it for |
| --- | --- |
| `auto-safe` | The default. Lets mpv pick a safe hardware decoder |
| `no` | Software (CPU) decoding. Good for testing, and for AV1 on older GPUs |
| `nvdec` | NVIDIA GPUs (Linux and Windows) |
| `vaapi` | AMD and Intel GPUs on Linux |
| `d3d11va` | Any GPU on Windows |

### Setting environment variables

**Linux (bash or zsh)**

```bash
MOSAIC_HWDEC=no MOSAIC_THREADS=1 python mosaic_wall.py ~/Videos
```

**Linux (fish)**

```fish
env MOSAIC_HWDEC=no MOSAIC_THREADS=1 python mosaic_wall.py ~/Videos
```

**Windows (PowerShell)**

```powershell
$env:MOSAIC_HWDEC = "no"; $env:MOSAIC_THREADS = "1"; python mosaic_wall.py "D:\My Videos"
```

**Windows (Command Prompt)**

```bat
set MOSAIC_HWDEC=no
set MOSAIC_THREADS=1
python mosaic_wall.py "D:\My Videos"
```

### NVIDIA + AMD/Intel laptops on Linux (hybrid graphics)

To decode on the NVIDIA GPU, run the whole app on it so decoding and rendering stay on the same card:

```bash
sudo pacman -S nvidia-utils nvidia-prime        # Arch; other distributions have equivalents
MOSAIC_HWDEC=nvdec prime-run python mosaic_wall.py
```

### Converting clips to H.264

**Linux (bash)**

```bash
mkdir -p converted
for f in Videos/*.{mkv,mp4,webm}; do
  ffmpeg -i "$f" -vf scale=-2:480 -c:v h264_nvenc -preset p5 -cq 28 -an "converted/$(basename "${f%.*}").mp4"
done
```

**Windows (PowerShell)**

```powershell
mkdir converted
Get-ChildItem Videos\* -Include *.mkv,*.mp4,*.webm | ForEach-Object {
  ffmpeg -i $_.FullName -vf scale=-2:480 -c:v h264_nvenc -preset p5 -cq 28 -an "converted\$($_.BaseName).mp4"
}
```

Replace `h264_nvenc` with `libx264 -preset veryfast -crf 26` if you have no NVIDIA GPU. Remove `-an` to keep
the audio. On Windows, [install ffmpeg](https://ffmpeg.org/download.html) first and make sure it is on your PATH.

## Troubleshooting

**Could not load mpv**
libmpv was not found. Reinstall it (Step 2). On Windows, make sure `libmpv-2.dll` sits next to
`mosaic_wall.py` and that Python and the DLL are both 64-bit. On Linux, run
`ldconfig -p | grep libmpv` to check it is installed.

**ModuleNotFoundError: No module named 'PySide6'**
The venv is not active, or the packages are not installed. Activate it (Step 3) and run
`pip install -r requirements.txt`.

**Windows: "running scripts is disabled on this system"**
Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` in PowerShell, or activate the venv from
Command Prompt with `venv\Scripts\activate.bat`.

**Qt error mentioning the "xcb" plugin (Linux)**
Install the xcb cursor library (`xcb-util-cursor` on Arch and Fedora, `libxcb-cursor0` on Debian, Ubuntu and
openSUSE). Run `QT_DEBUG_PLUGINS=1 python mosaic_wall.py` to see exactly what is missing.

**Videos open in separate mpv windows instead of inside the grid (Linux)**
mpv can only embed into an X11 window. The script forces X11/XWayland automatically, so make sure
XWayland is installed. If it still happens, change `gpu_context="x11egl"` to `"x11"` in `mosaic_wall.py`.

**Black or glitchy tiles**
Usually the hardware decoder. Test with `MOSAIC_HWDEC=no`. If that fixes it, install your GPU's video
decode drivers (`libva-utils` and `vainfo` on AMD/Intel on Linux, up-to-date graphics drivers on Windows).

**Right-click, dragging or double-click does nothing**
These use a nearly transparent overlay window on top of the wall. It needs a desktop compositor, which
every current KDE, GNOME and Windows session has. On tiling window managers, set a floating rule for the
app's windows. Otherwise please open an issue with your operating system, desktop environment and session type if it doesn't work.

**Stuttering with many tiles**
Lower the tile count, compress the videos to a smaller resolution, or set `MOSAIC_THREADS=1`.

## Contributing

If you wish to initiate issues and pull requests, please include your operating system, desktop environment,
GPU and the output of `python --version` when reporting a bug.

## Credits

Things that are used in this python script

[mpv](https://mpv.io)

[python-mpv](https://github.com/jaseg/python-mpv) 

[PySide6](https://doc.qt.io/qtforpython-6/)
