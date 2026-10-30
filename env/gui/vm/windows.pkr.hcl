packer {
  required_plugins {
    qemu = {
      source  = "github.com/hashicorp/qemu"
      version = "= 1.1.6"
    }
  }
}

variable "iso_url" { type = string }
variable "iso_checksum" { type = string }
variable "output_directory" { type = string }
variable "bundle_path" { type = string }
variable "build_password" {
  type      = string
  sensitive = true
}
variable "accelerator" {
  type    = string
  default = "tcg"
}

variable "windows_image_name" { type = string }
variable "tpm_socket" { type = string }

source "qemu" "windows" {
  iso_url           = var.iso_url
  iso_checksum      = var.iso_checksum
  output_directory  = var.output_directory
  vm_name           = "windows-materials-v1.qcow2"
  format            = "qcow2"
  accelerator       = var.accelerator
  machine_type      = "q35"
  cpu_model         = "max"
  cpus              = 4
  memory            = 8192
  disk_size         = "100G"
  disk_interface    = "sata"
  cdrom_interface   = "sata"
  net_device        = "e1000"
  headless          = true
  efi_boot          = true
  efi_firmware_code = "/usr/share/OVMF/OVMF_CODE_4M.fd"
  efi_firmware_vars = "/usr/share/OVMF/OVMF_VARS_4M.fd"
  efi_drop_efivars   = false
  communicator      = "winrm"
  winrm_username    = "Docker"
  winrm_password    = var.build_password
  winrm_timeout     = "3h"
  winrm_use_ssl     = false
  shutdown_command  = "powershell -NoProfile -Command \"Set-Service WinRM -StartupType Disabled; shutdown /s /t 10 /f\""
  shutdown_timeout  = "15m"
  cd_label          = "SGBSEED"
  cd_content = {
    "Autounattend.xml" = templatefile("${path.root}/config/windows-autounattend.pkrtpl", {
      password   = var.build_password
      image_name = var.windows_image_name
    })
    "bootstrap.ps1" = file("${path.root}/config/windows-bootstrap.ps1")
  }
  boot_wait    = "2s"
  boot_command = ["<spacebar><wait1><spacebar><wait1><spacebar>"]
  qemuargs = [
    ["-vga", "std"],
    ["-global", "VGA.xres=1920"],
    ["-global", "VGA.yres=1080"],
    ["-usb"],
    ["-device", "usb-tablet"],
    ["-chardev", "socket,id=chrtpm,path=${var.tpm_socket}"],
    ["-tpmdev", "emulator,id=tpm0,chardev=chrtpm"],
    ["-device", "tpm-tis,tpmdev=tpm0"]
  ]
}

build {
  sources = ["source.qemu.windows"]
  provisioner "file" {
    source      = var.bundle_path
    destination = "C:/Windows/Temp/scientific-software-operation.zip"
  }
  provisioner "powershell" {
    inline = [
      "Expand-Archive -Path C:/Windows/Temp/scientific-software-operation.zip -DestinationPath C:/scientific-software-operation-build",
      "& C:/scientific-software-operation-build/scientific-software-operation/scripts/windows.ps1"
    ]
  }
  provisioner "windows-restart" {
    restart_timeout = "20m"
  }
  provisioner "powershell" {
    inline = [
      "& C:/scientific-software-operation-build/scientific-software-operation/scripts/windows-check.ps1",
      "Remove-Item -Recurse -Force C:/scientific-software-operation-build",
      "Remove-Item -Force C:/Windows/Temp/scientific-software-operation.zip"
    ]
  }
}
