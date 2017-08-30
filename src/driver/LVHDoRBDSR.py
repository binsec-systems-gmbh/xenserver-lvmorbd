#!/usr/bin/python

# LVHDoRBDSR XenServer driver of LVM (LVHD) over RBD (Ceph)
#
# Copyright (C) 2017 binsec GmbH <info@binsec.com>
# 
# This library is free software; you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the Free
# Software Foundation; version 2.1 only.
# 
# This library is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. See the GNU Lesser General Public License for more details.
# 
# You should have received a copy of the GNU Lesser General Public License along
# with this library; if not, write to the Free Software Foundation, Inc., 51
# Franklin St, Fifth Floor, Boston, MA 02110, USA

import LVHDSR, VDI, scsiutil, SR, SRCommand, util, xs_errors, xmlrpclib, LUNperVDI 
import socket, os, copy

CAPABILITIES = ['SR_PROBE','VDI_CREATE','VDI_DELETE','VDI_ATTACH',
                'VDI_DETACH', 'VDI_CLONE', 'VDI_SNAPSHOT', 'VID_RESIZE',
                'VDI_INTRODUCE']

CONFIGURATION = [ [ 'image', 'The rbd image name' ], \
                  [ 'target', 'IP address or hostname of the ceph monitor' ], \
                  [ 'pool', 'The rbd pool name' ], \
                  [ 'auth', 'The ssh username' ], \
                  [ 'port', 'The monitor port number (default 6789) ' ], \
                  [ 'multihomed', 'Enable multi-homing to this target, true or false (optional, defaults to same value as host.other_config:multipathing)' ],
                  [ 'force_tapdisk', 'Force use of tapdisk, true or false (optional, defaults to false)'],
]

DRIVER_INFO = {
    'name': 'LVHDoRBD',
    'description': 'SR plugin which creates LVHDs on top of RBD object.',
    'vendor': 'binsec GmbH',
    'copyright': '(C) 2017 binsec GmbH',
    'driver_version': '1.0',
    'required_api_version': '1.0',
    'capabilities': CAPABILITIES,
    'configuration': CONFIGURATION
    }

MAXPORT = 65535
MAX_TIMEOUT = 15
MAX_LUNID_TIMEOUT = 60

DEFAULT_PORT = 6789

class LVHDoRBDSR(LVHDSR.LVHDSR):
    def handles(type):
        if type == 'lvmorbd':
            return True
        return False
    handles = staticmethod(handles)

    def load(self, sr_uuid):
        required = ['target', 'pool', 'image', 'user', 'auth']
        for item in required:
          if not self.dconf.has_key(item) or not self.dconf[item]:
              raise xs_errors.XenError('ConfigParamsMissing')

        if not self.dconf.has_key('port'):
            self.dconf['port'] = DEFAULT_PORT

        targets = []
        try:
            target_string = self.dconf['target'].split(',')
            for target in self.dconf['target'].split(','):
              address = util._convertDNS(target)
              if ':' in address:
                targets.append('[%s]' % address)
              else:
                target.append(address)
            util.SMlog('successfully resolved addresses to %s' % targets)
            self.targetlist = ','.join(targets)
            self.target = targets[0]
            self.dconf['targetlist'] = self.targetlist
        except:
            raise xs_errors.XenError('DNSError')
            
        if self.dconf.has_key('pool') and not self.dconf.has_key('image'):
            raise Exception('Only CLI with all parameters supported')
        elif self.dconf.has_key('image'):
            self.attached = os.path.exists('/dev/disk/by-id/scsi-%s' % self.dconf['image'])
            self.path = '/dev/disk/by-id/scsi-%s' % self.dconf['image']
            if os.path.exists('/var/lock/sm/%s/sr' % sr_uuid) and not self.attached:
                self.attach(sr_uuid)
                
        else:
            raise Exception('Only CLI with all parameters supported')
        self.dconf['device'] = self.path
        LVHDSR.LVHDSR.load(self, sr_uuid)
            
    def _getRBDIndex(self, name):
      import glob
      for device in glob.glob('/sys/bus/rbd/devices/*/name'):
        with open(device, 'rt') as fname:
          rbd_name = fname.readline()
        if name == rbd_name.strip():
          index = device.split('/')[5]
          util.SMlog('Found index %s for %s' % (index, name))
          return index
      util.SMlog('No index for %s found' % name)
      return None

    def create(self, sr_uuid, size):
      if not os.path.exists('/dev/disk/by-id/scsi-%s' % self.dconf['image']):
          self.attach(sr_uuid)
      LVHDSR.LVHDSR.create(self, sr_uuid, size)

    def attach(self, sr_uuid):
        rbd_index = self._getRBDIndex(self.dconf['image'])
        if self.dconf.has_key('image') and \
           self.dconf['image'] and \
           os.path.exists('/dev/rbd%s' % rbd_index):
            self.attached = True 
            return
        
        if self.dconf.has_key('image') and self.dconf['image']:
            rbd_image = self.dconf['image']
            for target in self.dconf['target'].split(','):
              util._testHost(target, long(self.dconf['port']), 'RBD Monitor')

            attach_string = '{targets} name={user},secret={secret} {pool} {image}'
            attach_values = {'targets': self.dconf['targetlist'],
                             'user': self.dconf['user'],
                             'secret': '<protected>',
                             'pool': self.dconf['pool'],
                             'image': rbd_image
                            }
            util.SMlog('Attach string: %s' % attach_string.format(**attach_values))
            attach_values['secret'] = self.dconf['auth']
            if not os.path.exists('/sys/bus/rbd'):
                os.execlp('modprobe', 'modprobe', 'rbd')
            rbd_disk_path =  '/dev/disk/by-id/scsi-%s' % rbd_image
            rbd_scsi_path =  '/dev/disk/by-scsid/%s' % rbd_image
            if not os.path.exists(rbd_disk_path) and not rbd_index:
                try:
                    with open('/sys/bus/rbd/add','w') as rbd_add:
                      rbd_add.write(attach_string.format(**attach_values))
                    #
                    # update rbd_index after attaching
                    #
                    rbd_index = self._getRBDIndex(self.dconf['image'])
                    os.symlink('/dev/rbd%s' % rbd_index , rbd_disk_path)
                    os.makedirs(rbd_scsi_path)
                    os.symlink('../../../rbd%s' % rbd_index, '%s/rbd%s' % (rbd_scsi_path, rbd_index))
                    self.attached = True
                    self.SCSIid = rbd_index
                except IOError, e:
                    util.SMlog('Attach thrown exception and the error is %s' % e)
                    self.attached = False
        else:
            self.attached = True
      
      
    def detach(self, sr_uuid):
        if self.dconf.has_key('image') and self.dconf['image']:
            rbd_image_name = self.dconf['image']
            rbd_disk_path =  '/dev/disk/by-id/scsi-%s' % rbd_image_name
            rbd_scsi_path =  '/dev/disk/by-scsid/%s' % rbd_image_name
            rbd_image_index = self._getRBDIndex(rbd_image_name)
            if os.path.exists(rbd_disk_path):
                os.unlink(rbd_disk_path)
            if os.path.exists(rbd_scsi_path):
                os.unlink('%s/rbd%s' % (rbd_scsi_path, rbd_image_index))
                os.rmdir(rbd_scsi_path)
            if os.path.exists('/dev/rbd%s' % rbd_image_index):
                try:
                    util.time.sleep(MAX_TIMEOUT) 
                    with open('/sys/bus/rbd/remove','w') as rem:
                        util.SMlog("Writing %s into rbd/remove" % rbd_image_index)
                        rem.write(rbd_image_index)
                        self.attached = False
                except IOError, e:
                    util.SMlog('Detach thrown exception and the error is %s' % e)
                    self.attached = True
      
      
    def refresh(self):
        pass

    def vdi(self, uuid):
        return LVHDoRBDVDI(self, uuid)

    def _attach_LUN_bySCSIid(self, SCSIid):
        if os.path.exists('/dev/disk/by-id/scsi-%s' % SCSIid):
            return True
        else:
            self.attach(self.uuid)
            return True


class LVHDoRBDVDI(LVHDSR.LVHDVDI):
    def generate_config(self, sr_uuid, vdi_uuid):
        if not lvutil._checkLV(self.path):
            raise xs_errors.XenError('VDIUnavailable')
        data = {'sr_uuid':        sr_uuid,
                'vdi_uuid':       vdi_uuid,
                'command':        'vdi_attach_from_config',
                'device_config':  self.sr.dconf
               }
        config = xmlrpclib.dumps(tuple([data]), 'vdi_attach_from_config')
        return xmlrpclib.dumps((config,), '', True)

    def attach_from_config(self, sr_uuid, vdi_uuid):
        try:
            self.sr.attach(sr_uuid)
            if not self.sr._attach_LUN_bySCSIid(self.sr.SCSIid):
                raise xs_errors.XenError('InvalidDev')
            return LVHDSR.LVHDVDI.attach(self, sr_uuid, vdi_uuid)
        except:
            util.logException('LVHDoRBDVDI.attach_from_config')
            raise xs_errors.XenError('SRUnavailable', opterr='Failed to attach RBD')

      
if __name__ == '__main__':
    SRCommand.run(LVHDoRBDSR, DRIVER_INFO)
else:
    SR.registerSR(LVHDoRBDSR)
