/*
 * Research-only helper: issue SYNOIO_SET_DISK_LED on /dev/synobios.
 * Compile for AArch64 guest; do not commit the binary.
 *
 * aarch64-linux-gnu-gcc -static -O2 -o synobios-set-disk-led synobios-set-disk-led.c
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

/* Proven from ds124 synobios.ko: _IOWR('K', 10, DISKLEDSTATUS) size 24. */
#define SYNOIO_SET_DISK_LED 0xc0184b0a

typedef struct {
    int diskno;
    int status;
    int iNodeNameLen;
    const char *szNodeName;
} DISKLEDSTATUS;

int main(int argc, char **argv)
{
    DISKLEDSTATUS st;
    int fd;
    int rc;
    const char *node = "sata1";

    memset(&st, 0, sizeof(st));
    st.diskno = (argc > 1) ? atoi(argv[1]) : 1;
    st.status = (argc > 2) ? atoi(argv[2]) : 1; /* SYNO_DISK_LED typically 0..4 */
    st.szNodeName = (argc > 3) ? argv[3] : node;
    st.iNodeNameLen = (int)strlen(st.szNodeName);

    fd = open("/dev/synobios", O_RDWR);
    if (fd < 0) {
        perror("open /dev/synobios");
        return 1;
    }
    printf("issuing SYNOIO_SET_DISK_LED=%#x diskno=%d status=%d node=%s\n",
           SYNOIO_SET_DISK_LED, st.diskno, st.status, st.szNodeName);
    fflush(stdout);
    rc = ioctl(fd, SYNOIO_SET_DISK_LED, &st);
    printf("ioctl rc=%d errno=%d (%s)\n", rc, errno, strerror(errno));
    close(fd);
    return rc < 0 ? 2 : 0;
}
