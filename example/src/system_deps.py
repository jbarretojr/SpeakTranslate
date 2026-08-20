import os
import shutil
import subprocess
import sys

REQUIRED_BINARIES = (
    "xdotool",
    "xclip",
)

REQUIRED_PACKAGES = (
    "portaudio19-dev",
    "libportaudio2",
)

NVIDIA_PACKAGES = (
    "libcublas12",
)

_PACKAGE_MANAGERS = (
    ('apt-get', lambda pkgs: ['apt-get', 'install', '-y', *pkgs]),
    ('dnf', lambda pkgs: ['dnf', 'install', '-y', *pkgs]),
    ('pacman', lambda pkgs: ['pacman', '-S', '--noconfirm', *pkgs]),
    ('zypper', lambda pkgs: ['zypper', '--non-interactive', 'install', *pkgs]),
)


def _missing_binaries():
    return [b for b in REQUIRED_BINARIES if shutil.which(b) is None]


def _missing_packages(packages):
    missing = []
    for pkg in packages:
        result = subprocess.run(
            ["dpkg", "-s", pkg],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            missing.append(pkg)
    return missing


def _has_nvidia_gpu():
    """Verifica se há uma GPU NVIDIA disponível no sistema."""
    return shutil.which("nvidia-smi") is not None and subprocess.run(
        ["nvidia-smi"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def _detect_install_command(packages):
    for manager, build_cmd in _PACKAGE_MANAGERS:
        if shutil.which(manager):
            return ['sudo', *build_cmd(packages)]
    return None


def _run_install(install_cmd):
    env = {**os.environ, 'DEBIAN_FRONTEND': 'noninteractive'}
    print(f'Instalando dependências: {" ".join(install_cmd)}')
    result = subprocess.run(install_cmd, env=env)
    return result.returncode == 0


def ensure_system_dependencies():
    """Verifica e instala ferramentas de sistema necessárias no Linux."""
    if sys.platform != 'linux':
        return True

    required = list(_missing_binaries()) + _missing_packages(REQUIRED_PACKAGES)

    if _has_nvidia_gpu():
        nvidia_missing = _missing_packages(NVIDIA_PACKAGES)
        if nvidia_missing:
            print('GPU NVIDIA detectada. Verificando dependências CUDA...')
            required += nvidia_missing
    else:
        print('GPU NVIDIA não detectada, pulando dependências CUDA.')

    if not required:
        return True

    print('Dependências de sistema ausentes:', ', '.join(required))

    install_cmd = _detect_install_command(required)
    if install_cmd is None:
        print(
            'Gerenciador de pacotes não suportado. Instale manualmente:\n'
            '  sudo apt install xdotool xclip portaudio19-dev'
        )
        return False

    if not _run_install(install_cmd):
        print('Falha ao instalar dependências de sistema.')
        return False

    still_missing = list(_missing_binaries()) + _missing_packages(REQUIRED_PACKAGES)
    if still_missing:
        print('Ainda ausentes após instalação:', ', '.join(still_missing))
        return False

    print('Dependências de sistema instaladas com sucesso.')
    return True