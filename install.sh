#!/bin/bash
# Скрипт для установки зависимостей с предкомпилированными пакетами

set -e

echo "🔧 Установка системных зависимостей..."

# Определяем ОС
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if command -v apt-get &> /dev/null; then
        echo "📦 Установка для Debian/Ubuntu..."
        sudo apt-get update
        sudo apt-get install -y build-essential llvm llvm-dev ffmpeg python3-dev
    elif command -v yum &> /dev/null; then
        echo "📦 Установка для CentOS/RHEL..."
        sudo yum install -y gcc gcc-c++ llvm llvm-devel ffmpeg python3-devel
    elif command -v pacman &> /dev/null; then
        echo "📦 Установка для Arch Linux..."
        sudo pacman -S --noconfirm base-devel llvm ffmpeg python
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo "📦 Установка для macOS..."
    if command -v brew &> /dev/null; then
        brew install llvm ffmpeg
    else
        echo "❌ Homebrew не установлен. Установите Homebrew: https://brew.sh"
        exit 1
    fi
else
    echo "⚠️  Автоматическая установка для вашей ОС не поддерживается."
    echo "Пожалуйста, установите вручную: LLVM, FFmpeg, build-essential"
fi

echo "✅ Системные зависимости установлены"
echo "📦 Установка Python зависимостей через Poetry..."

poetry install

echo "✅ Установка завершена!"
