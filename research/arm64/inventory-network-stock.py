#!/usr/bin/env python3
"""Inventory the supplied DS124 kernel and official root archive, never upstream substitutes."""
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import struct
import tarfile

WORK = Path(__file__).resolve().parent / 'work'
HOST = ('usb-common', 'usbcore', 'xhci-hcd', 'xhci-plat-hcd', 'dwc3', 'dwc3_rtk', 'dwc2', 'ehci-hcd', 'ehci-platform', 'ehci-pci', 'ohci-hcd', 'ohci-platform', 'rtk-usb-manager', 'phy-rtk-usb2', 'phy-rtk-usb3')
NET = ('usbnet', 'cdc_ether', 'cdc_ncm', 'cdc_mbim', 'rndis_host', 'rndis_wlan', 'asix', 'ax88179_178a', 'rtl8150', 'r8152', 'smsc75xx', 'smsc95xx', 'pegasus', 'net1080', 'cdc_subset', 'zaurus', 'r8168', 'stmmac', 'dwmac', 'macb', 'lan9118', 'virtio_net')


def sections(raw):
    if raw[:6] != b'\x7fELF\x02\x01':
        raise ValueError('Expected little endian ELF64')
    offset = struct.unpack_from('<Q', raw, 40)[0]
    stride, count, names = struct.unpack_from('<HHH', raw, 58)
    headers = [struct.unpack_from('<IIQQQQIIQQ', raw, offset + i * stride) for i in range(count)]
    h = headers[names]
    table = raw[h[4]:h[4] + h[5]]
    return {table[h[0]:].split(b'\0', 1)[0].decode(): raw[h[4]:h[4] + h[5]] for h in headers if h[1] != 8}


def main():
    output = WORK / 'network-stock'
    output.mkdir(exist_ok=True)
    modules = {}
    metadata = {}
    policies = []
    with tarfile.open(WORK / 'extracted/hda1.tgz', 'r:*') as archive:
        for member in archive:
            name = member.name.lstrip('./')
            if not member.isfile():
                continue
            base = Path(name).name
            if name.endswith('.ko') and base[:-3] in HOST + NET:
                raw = archive.extractfile(member).read()
                sec = sections(raw)
                info = [x.decode('utf-8', 'replace') for x in sec.get('.modinfo', b'').split(b'\0') if x]
                dest = output / base
                dest.write_bytes(raw)
                modules[base[:-3]] = dict(path=name, sha256=hashlib.sha256(raw).hexdigest(), modinfo=info,
                    symbols=[x.decode('utf-8', 'replace') for x in sec.get('.strtab', b'').split(b'\0') if x],
                    strings=[x.decode('ascii') for x in re.findall(rb'[\x20-\x7e]{4,}', raw)])
            elif base in ('modules.alias', 'modules.dep', 'modules.builtin', 'modules.builtin.modinfo'):
                metadata[name] = archive.extractfile(member).read().decode('utf-8', 'replace')
            elif member.size < 200000 and 'synoman/' not in name and any(key in name.lower() for key in ('synoinfo.conf', 'udev/rules.d', 'network', 'netif', 'usb', 'syno_module', 'initeth', 'synonet', 'dhcp')):
                if not name.endswith(('.so', '.a', '.ko')):
                    raw = archive.extractfile(member).read()
                    if b'\0' not in raw:
                        text = raw.decode('utf-8', 'replace')
                        policies.append((name, text))
    kallsyms = (WORK / 'ds124.kallsyms').read_text()
    kernel = (WORK / 'boot/zImage.Image').read_bytes()
    kernel_strings = [x.decode('ascii') for x in re.findall(rb'[\x20-\x7e]{4,}', kernel)]
    recovered_symbols = [x.decode('utf-8', 'replace') for x in sections((WORK / 'recovered.elf').read_bytes()).get('.strtab', b'').split(b'\0') if x]
    init_modules = sorted(p.name for p in (WORK / 'initrd').rglob('*.ko'))
    report = dict(stock='DSM_DS124_72806.pat', recovered_elf_sha256=hashlib.sha256((WORK / 'recovered.elf').read_bytes()).hexdigest(), modules=modules, initramfs_modules=init_modules,
                  module_metadata=metadata)
    (output / 'inventory.json').write_text(json.dumps(report, indent=2) + '\n')
    for filename, keys in [('usb-host-driver-map.txt', HOST), ('usb-net-driver-map.txt', NET)]:
        lines = ['Stock DS124 DSM 72806 only. No upstream kernel support used as evidence.',
                 ('Controller | Driver | Compatible | Built-in/module | Evidence' if keys == HOST else 'Protocol/device | Driver | Built-in/module | USB IDs / aliases | Evidence')]
        for key in keys:
            module = modules.get(key)
            if module:
                aliases = [x[6:] for x in module['modinfo'] if x.startswith('alias=')]
                deps = [x for x in module['modinfo'] if x.startswith(('depends=', 'vermagic='))]
                fields = [key, key, '; '.join(aliases) or '(no alias)', f"module (initramfs={'yes' if key+'.ko' in init_modules else 'no'})", f"{module['path']}; sha256={module['sha256']}; {'; '.join(deps)}"]
                if keys == NET:
                    fields[2], fields[3] = fields[3], fields[2]
                lines.append(' | '.join(fields))
            else:
                hits = [x for x in kallsyms.splitlines() if key.replace('-', '_') in x or key in x]
                lines.append(f"{key} | no supplied module | - | {'symbol matches need verification' if hits else 'not found'} | {len(hits)} kallsyms matches; no module in full hda1.tgz/initramfs inventory")
        lines += ['', 'Module metadata files present: ' + (', '.join(metadata) or 'NONE')]
        lines += ['', 'Kernel evidence (strings/symbols do not alone prove a probe contract):']
        rx = re.compile('xhci|ehci|ohci|dwc[23]|usbcore|usb_common|usb_register|hub_init|usbnet|cdc_ether|rndis|r8169|stmmac|dwmac|macb|lan9118|virtio_net', re.I)
        lines += ['SYMBOL ' + x for x in kallsyms.splitlines() if rx.search(x)]
        lines += ['ELF_SYMBOL ' + x for x in recovered_symbols if rx.search(x)]
        lines += ['STRING ' + x for x in kernel_strings if rx.search(x)]
        (WORK / filename).write_text('\n'.join(lines) + '\n')
    with (WORK / 'network-policy-stock.txt').open('w') as report:
        for name, text in policies:
            report.write('\n===== ' + name + ' =====\n' + text + '\n')
    for key in ('usbcore', 'xhci-plat-hcd', 'usbnet', 'cdc_ether'):
        module = modules.get(key)
        print(key, module['modinfo'] if module else 'ABSENT')
    cdc_alias = 'usb:v0525pA4A2d0000dc02dsc00dp00ic02isc06ip00in00'
    matching = [a for a in modules['cdc_ether']['modinfo'] if a.startswith('alias=') and fnmatch.fnmatchcase(cdc_alias, a[6:])]
    assert matching, 'Supplied CDC module must match the exact QEMU interface'
    assert any('ic02isc06ip00in* cdc_ether' in line for line in metadata['usr/lib/modules/modules.alias'].splitlines()), 'Stock modules.alias must enable class binding'
    print('Exact CDC alias matched:', matching)
    print('Metadata files:', list(metadata))
    print('Inventory:', output / 'inventory.json')


if __name__ == '__main__':
    main()
