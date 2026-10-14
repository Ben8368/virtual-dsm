# External hardware breakpoints for the recovered stock DS124 72806 Image.
# This captures execution without changing the kernel, initramfs or root payload.
set pagination off
set confirm off
set architecture aarch64
target remote 127.0.0.1:12347
python
import gdb
import struct
regs_by_sp = {}
pending = {}

def reg(name):
    return int(gdb.parse_and_eval('$' + name)) & 0xffffffffffffffff

def u64(addr):
    return struct.unpack('<Q', bytes(gdb.selected_inferior().read_memory(addr, 8)))[0]

def text(addr):
    if not addr:
        return ''
    result = bytearray()
    while len(result) < 4096:
        try:
            chunk = bytes(gdb.selected_inferior().read_memory(addr + len(result), 64))
        except gdb.MemoryError:
            chunk = bytes(gdb.selected_inferior().read_memory(addr + len(result), 1))
        end = chunk.find(b'\x00')
        if end >= 0:
            result.extend(chunk[:end])
            return result.decode('utf-8', 'replace')
        result.extend(chunk)
    return result.decode('utf-8', 'replace')

class UserEntry(gdb.Breakpoint):
    def __init__(self, pc, path):
        super().__init__(f'*{pc:#x}', type=gdb.BP_HARDWARE_BREAKPOINT, internal=True, temporary=True)
        self.path = path
    def stop(self):
        self.enabled = False
        gdb.write(f'USER_ENTRY path={self.path} PC={reg("pc"):#x}; first executable instruction reached\n')
        return False

class ExecEntry(gdb.Breakpoint):
    def stop(self):
        regs_by_sp[reg('sp') - 32] = reg('x0')
        return False

class ExecName(gdb.Breakpoint):
    def stop(self):
        try:
            path = text(u64(reg('x1')))
            gdb.write(f'EXECVE_NAME path={path}\n')
            if path.startswith('/tmpRoot/'):
                stack = reg('sp')
                registers = regs_by_sp[stack]
                pending[stack] = (path, registers)
                gdb.write(f'ROOT_EXECVE path={path} kernel_sp={stack:#x}\n')
                # TTBR0/PAN can prevent reading user argv while stopped in EL1.
                # This must not suppress kernel pathname or successful exec proof.
                try:
                    argv = []
                    argp = u64(registers + 8)
                    for i in range(16):
                        item = u64(argp + i * 8)
                        if not item: break
                        argv.append(text(item))
                    gdb.write(f'ROOT_EXECVE_ARGV {argv!r}\n')
                except (gdb.MemoryError, OverflowError):
                    gdb.write('ROOT_EXECVE_ARGV unreadable in kernel context\n')

        except (gdb.MemoryError, OverflowError, KeyError) as error:
            gdb.write(f'EXECVE_CAPTURE_WARNING {error}\n')
        return False

class ExecReturn(gdb.Breakpoint):
    def stop(self):
        item = pending.pop(reg('sp'), None)
        if item:
            path, registers = item
            rc = reg('x0') & 0xffffffff
            if rc >= 0x80000000: rc -= 0x100000000
            pc = u64(registers + 256)
            gdb.write(f'ROOT_EXECVE_RETURN path={path} rc={rc} new_user_pc={pc:#x}\n')
            if rc == 0:
                UserEntry(pc, path)
        return False

class RootOperation(gdb.Breakpoint):
    def __init__(self, address, label):
        super().__init__(f'*{address:#x}', type=gdb.BP_HARDWARE_BREAKPOINT, internal=True)
        self.label = label
    def stop(self):
        try:
            path = text(u64(reg('x0')))
            gdb.write(f'ROOT_OPERATION {self.label} path={path!r}\n')
        except (gdb.MemoryError, OverflowError, KeyError):
            gdb.write(f'ROOT_OPERATION {self.label}; path unreadable\n')
        return False

ExecEntry('*0xffffffc010280914', type=gdb.BP_HARDWARE_BREAKPOINT, internal=True)
ExecName('*0xffffffc010280940', type=gdb.BP_HARDWARE_BREAKPOINT, internal=True)
ExecReturn('*0xffffffc01028095c', type=gdb.BP_HARDWARE_BREAKPOINT, internal=True)
RootOperation(0xffffffc01026f634, 'chroot')
RootOperation(0xffffffc0102abe40, 'pivot_root')
end
continue
