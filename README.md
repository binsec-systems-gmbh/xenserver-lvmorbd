# xenserver-lvmorbd

This plugin provides an additional SR driver for XenServer 7.1.
The driver adds support for LVM (LVHD) over RBD (Ceph).

The driver adds a new type for the sr-create command. XenCenter is not
supported.

## License
GNU Lesser General Public License as published by the Free Software Foundation; version 2.1 only. 
Equal to other drivers from XenServer.

## Disclaimer
**Use this driver at own risk!** The binsec GmbH wants to make certain
that everyone understands that there is no warranty for this free software.
binsec GmbH will not be responsible for any data loss or other damage caused by this software.

## Install
Download the lvmorbd.iso from the isos directory.

Mount the iso on the XenServer:
```
mount -o loop lvmorbd.iso /mnt
```

Before installation, take a look on the install script. It will activate the rbd
kernel module, install the LVMoRBDSR driver and add the lvmorbd type to allowed
plugins.

To install the driver, run install and restart the xe-toolstack:
```
cd /mnt
./install
xe-toolkit-restart
```

## Usage

To create a new SR use the regular sr-create command:
```
xe sr-create type=lvmorbd name-label=<label> shared=true \
device-config:target=<comma separated list of monitors> \
device-config:pool=<pool name> device-config:image=<image name> \
device-config:user=<cephx user> device-config:auth=<cephx key>
```

## Credits
The idea of the driver to connect RBD devices without the requirement of the
ceph userland on the XenServer is based on the rbdsr driver from Mark
Starikov(mr.mark.starikov@gmail.com) (see: https://github.com/mstarikov/rbdsr).
