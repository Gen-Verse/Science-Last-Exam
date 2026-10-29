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
variable "profile_name" {
  type = string
  default = "linux-desktop-v1"
}
variable "build_password" {
  type      = string
  sensitive = true
}
variable "accelerator" {
  type    = string
  default = "tcg"
}

variable "password_hash" {
  type      = string
  sensitive = true
}

source "qemu" "linux" {
  iso_url          = var.iso_url
  iso_checksum     = var.iso_checksum
  output_directory = var.output_directory
  vm_name          = "${var.profile_name}.qcow2"
  format           = "qcow2"
  accelerator      = var.accelerator
  cpu_model        = "max"
  cpus             = 4
  memory           = 8192
  disk_size        = "80G"
  disk_interface   = "ide"
  net_device       = "e1000"
  headless         = true
  ssh_username     = "user"
  ssh_password     = var.build_password
  ssh_timeout      = "3h"
  shutdown_command = "sudo -n shutdown -P now"
  shutdown_timeout = "10m"
  cd_label         = "cidata"
  cd_content = {
    "meta-data" = "instance-id: scientific-gui-build\nlocal-hostname: scientific-gui\n"
    "user-data" = templatefile("${path.root}/config/linux-user-data.pkrtpl", {
      password_hash = var.password_hash
    })
  }
  boot_wait = "10s"
  boot_command = [
    "<esc><wait>c<wait>",
    "linux /casper/vmlinuz autoinstall ds=nocloud ---<enter><wait>",
    "initrd /casper/initrd<enter><wait>",
    "boot<enter>"
  ]
  qemuargs = [
    ["-vga", "std"],
    ["-global", "VGA.xres=1920"],
    ["-global", "VGA.yres=1080"]
  ]
}

build {
  sources = ["source.qemu.linux"]
  provisioner "file" {
    source      = var.bundle_path
    destination = "/tmp/scientific-gui.tar.gz"
  }
  provisioner "shell" {
    inline = [
      "sudo -n mkdir -p /opt/scientific-gui-build",
      "sudo -n tar -xzf /tmp/scientific-gui.tar.gz -C /opt/scientific-gui-build",
      "sudo -n chown -R user:user /opt/scientific-gui-build",
      "cd /opt/scientific-gui-build/scientific-gui && bash scripts/linux.sh"
    ]
  }
}
