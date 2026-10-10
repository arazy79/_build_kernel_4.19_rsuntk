#!/usr/bin/env python3
"""
Finish the SUSFS kernel patch (50_add_susfs_in_kernel-4.19.patch) on a tree
where 4 files get rejected hunks:
  include/linux/mount.h, fs/proc/cmdline.c, fs/proc/task_mmu.c, fs/namespace.c
Run from the kernel source root, right after `patch -p1` (even if it failed).
Idempotent: safe to run more than once.

Usage:
  python3 susfs_fixup_4.19.py susfs   (default) finish the SUSFS kernel patch
  python3 susfs_fixup_4.19.py hooks   finish the KSU manual hook patch
                                      (fs/exec.c, drivers/input/input.c)
"""
import os
import re
import sys

FAILED = []


def read(path):
    with open(path, encoding="utf-8", errors="surrogateescape") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(text)


def lines(*items):
    return "\n".join(items) + "\n"


def edit(path, old, new, marker, what):
    if not os.path.exists(path):
        print("[FAIL] %s: file not found (%s)" % (path, what))
        FAILED.append(path)
        return
    text = read(path)
    if marker in text:
        print("[skip] %s: %s already present" % (path, what))
        return
    count = text.count(old)
    if count != 1:
        print("[FAIL] %s: %s: anchor found %d times" % (path, what, count))
        FAILED.append(path)
        return
    write(path, text.replace(old, new, 1))
    print("[ok]   %s: %s" % (path, what))




def edit_re(path, pattern, repl, marker, what):
    if not os.path.exists(path):
        print("[FAIL] %s: file not found (%s)" % (path, what))
        FAILED.append(path)
        return
    text = read(path)
    if marker in text:
        print("[skip] %s: %s already present" % (path, what))
        return
    new, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        print("[FAIL] %s: %s: pattern not found" % (path, what))
        FAILED.append(path)
        return
    write(path, new)
    print("[ok]   %s: %s" % (path, what))

def fix_susfs():
    # ---------------------------------------------------------------- mount.h
    edit(
        "include/linux/mount.h",
        lines(
            "\tANDROID_KABI_RESERVE(3);",
            "\tANDROID_KABI_RESERVE(4);",
            "} __randomize_layout;",
        ),
        lines(
            "\tANDROID_KABI_RESERVE(3);",
            "#ifdef CONFIG_KSU_SUSFS",
            "\tANDROID_KABI_USE(4, u64 susfs_mnt_id_backup);",
            "#else",
            "\tANDROID_KABI_RESERVE(4);",
            "#endif",
            "} __randomize_layout;",
        ),
        "susfs_mnt_id_backup",
        "susfs_mnt_id_backup field",
    )

    # ------------------------------------------------------------- cmdline.c
    edit(
        "fs/proc/cmdline.c",
        lines(
            "#include <asm/setup.h>",
            "",
            "#ifdef CONFIG_INITRAMFS_IGNORE_SKIP_FLAG",
        ),
        lines(
            "#include <asm/setup.h>",
            "",
            "#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG",
            "extern int susfs_spoof_cmdline_or_bootconfig(struct seq_file *m);",
            "#endif",
            "",
            "#ifdef CONFIG_INITRAMFS_IGNORE_SKIP_FLAG",
        ),
        "extern int susfs_spoof_cmdline_or_bootconfig",
        "extern declaration",
    )
    edit(
        "fs/proc/cmdline.c",
        lines(
            "static int cmdline_proc_show(struct seq_file *m, void *v)",
            "{",
            "\tseq_puts(m, proc_command_line);",
        ),
        lines(
            "static int cmdline_proc_show(struct seq_file *m, void *v)",
            "{",
            "#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG",
            "\tif (!susfs_spoof_cmdline_or_bootconfig(m)) {",
            "\t\tseq_putc(m, '\\n');",
            "\t\treturn 0;",
            "\t}",
            "#endif",
            "\tseq_puts(m, proc_command_line);",
        ),
        "if (!susfs_spoof_cmdline_or_bootconfig(m))",
        "cmdline spoof hook",
    )

    # ----------------------------------------------------------- task_mmu.c
    edit(
        "fs/proc/task_mmu.c",
        lines(
            "#include <linux/ctype.h>",
            "",
            "#include <asm/elf.h>",
        ),
        lines(
            "#include <linux/ctype.h>",
            "#if defined(CONFIG_KSU_SUSFS_SUS_KSTAT) || defined(CONFIG_KSU_SUSFS_SUS_MAP)",
            "#include <linux/susfs_def.h>",
            "#endif",
            "",
            "#include <asm/elf.h>",
        ),
        "linux/susfs_def.h",
        "susfs_def.h include",
    )

    # ----------------------------------------------------------- namespace.c
    NS = "fs/namespace.c"

    edit(
        NS,
        lines(
            "#include <linux/fs_context.h>",
            "",
            '#include "pnode.h"',
            '#include "internal.h"',
        ),
        lines(
            "#include <linux/fs_context.h>",
            "#if defined(CONFIG_KSU_SUSFS_SUS_MOUNT) || defined(CONFIG_KSU_SUSFS_TRY_UMOUNT)",
            "#include <linux/susfs_def.h>",
            "#endif",
            "",
            '#include "pnode.h"',
            '#include "internal.h"',
            "",
            "#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT",
            "extern bool susfs_is_current_ksu_domain(void);",
            "extern bool susfs_is_current_zygote_domain(void);",
            "",
            "static DEFINE_IDA(susfs_mnt_id_ida);",
            "static DEFINE_IDA(susfs_mnt_group_ida);",
            "",
            "#define CL_ZYGOTE_COPY_MNT_NS BIT(24) /* used by copy_mnt_ns() */",
            "#define CL_COPY_MNT_NS BIT(25) /* used by copy_mnt_ns() */",
            "#endif",
            "",
            "#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT",
            "extern void susfs_auto_add_sus_ksu_default_mount(const char __user *to_pathname);",
            "bool susfs_is_auto_add_sus_ksu_default_mount_enabled = true;",
            "#endif",
            "#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT",
            "extern int susfs_auto_add_sus_bind_mount(const char *pathname, struct path *path_target);",
            "bool susfs_is_auto_add_sus_bind_mount_enabled = true;",
            "#endif",
            "#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT",
            "extern void susfs_auto_add_try_umount_for_bind_mount(struct path *path);",
            "bool susfs_is_auto_add_try_umount_for_bind_mount_enabled = true;",
            "#endif",
        ),
        "susfs_is_current_zygote_domain(void);",
        "includes + susfs declarations",
    )

    edit(
        NS,
        '\tmnt = alloc_vfsmnt(fc->source ?: "none");\n',
        lines(
            "#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT",
            "\t/* For newly created mounts, the only caller process we care is KSU */",
            "\tif (unlikely(susfs_is_current_ksu_domain())) {",
            '\t\tmnt = alloc_vfsmnt(fc->source ?: "none", true, 0);',
            "\t\tgoto bypass_orig_flow;",
            "\t}",
            '\tmnt = alloc_vfsmnt(fc->source ?: "none", false, 0);',
            "bypass_orig_flow:",
            "#else",
            '\tmnt = alloc_vfsmnt(fc->source ?: "none");',
            "#endif",
        ),
        'alloc_vfsmnt(fc->source ?: "none", true, 0)',
        "vfs_create_mount hook",
    )

    edit(
        NS,
        lines(
            "\tstruct mount *mnt;",
            "\tint err;",
            "",
            "\tmnt = alloc_vfsmnt(old->mnt_devname);",
        ),
        lines(
            "\tstruct mount *mnt;",
            "\tint err;",
            "#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT",
            "\tbool is_current_ksu_domain = susfs_is_current_ksu_domain();",
            "\tbool is_current_zygote_domain = susfs_is_current_zygote_domain();",
            "",
            "\t/* - CL_COPY_MNT_NS tells a copy_tree() (unshare) from a single clone",
            "\t * - KSU process: not unsharing => new sus mnt_id; unsharing => spoof with old mnt_id",
            "\t * - zygote process and old mnt_id is sus => new sus mnt_id",
            "\t * - other process unsharing => new sus mnt_id only for old sus mounts",
            "\t */",
            "\tif (unlikely(is_current_ksu_domain)) {",
            "\t\tif (!(flag & CL_COPY_MNT_NS)) {",
            "\t\t\tmnt = alloc_vfsmnt(old->mnt_devname, true, 0);",
            "\t\t\tgoto bypass_orig_flow;",
            "\t\t}",
            "\t\tmnt = alloc_vfsmnt(old->mnt_devname, true, old->mnt_id);",
            "\t\tif (mnt) {",
            "\t\t\tmnt->mnt.susfs_mnt_id_backup = DEFAULT_SUS_MNT_ID_FOR_KSU_PROC_UNSHARE;",
            "\t\t}",
            "\t\tgoto bypass_orig_flow;",
            "\t}",
            "\tif (likely(is_current_zygote_domain) && (old->mnt_id >= DEFAULT_SUS_MNT_ID)) {",
            "\t\tmnt = alloc_vfsmnt(old->mnt_devname, true, 0);",
            "\t\tgoto bypass_orig_flow;",
            "\t}",
            "\tif ((flag & CL_COPY_MNT_NS) && (old->mnt_id >= DEFAULT_SUS_MNT_ID)) {",
            "\t\tmnt = alloc_vfsmnt(old->mnt_devname, true, 0);",
            "\t\tgoto bypass_orig_flow;",
            "\t}",
            "\tmnt = alloc_vfsmnt(old->mnt_devname, false, 0);",
            "bypass_orig_flow:",
            "#else",
            "\tmnt = alloc_vfsmnt(old->mnt_devname);",
            "#endif",
        ),
        "bool is_current_ksu_domain = susfs_is_current_ksu_domain();",
        "clone_mnt alloc hook",
    )

    edit(
        NS,
        lines(
            "\tmnt->mnt.mnt_root = dget(root);",
            "\tmnt->mnt_mountpoint = mnt->mnt.mnt_root;",
            "\tmnt->mnt_parent = mnt;",
            "\tlock_mount_hash();",
        ),
        lines(
            "\tmnt->mnt.mnt_root = dget(root);",
            "\tmnt->mnt_mountpoint = mnt->mnt.mnt_root;",
            "\tmnt->mnt_parent = mnt;",
            "",
            "#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT",
            "\t/* zygote and not unsharing: just reorder the mnt_id */",
            "\tif (likely(is_current_zygote_domain) && !(flag & CL_ZYGOTE_COPY_MNT_NS)) {",
            "\t\tmnt->mnt.susfs_mnt_id_backup = mnt->mnt_id;",
            "\t\tmnt->mnt_id = current->susfs_last_fake_mnt_id++;",
            "\t}",
            "#endif",
            "",
            "\tlock_mount_hash();",
        ),
        "current->susfs_last_fake_mnt_id++",
        "clone_mnt zygote mnt_id reorder",
    )


def fix_hooks():
    # fs/exec.c: tolerant to an extra blank line after "{"
    edit(
        "fs/exec.c",
        "static int do_execveat_common(int fd, struct filename *filename,\n",
        lines(
            "#ifdef CONFIG_KSU",
            "extern bool ksu_execveat_hook __read_mostly;",
            "extern int ksu_handle_execveat(int *fd, struct filename **filename_ptr, void *argv,",
            "\t\t\tvoid *envp, int *flags);",
            "extern int ksu_handle_execveat_sucompat(int *fd, struct filename **filename_ptr,",
            "\t\t\t\t void *argv, void *envp, int *flags);",
            "#endif",
            "static int do_execveat_common(int fd, struct filename *filename,",
        ),
        "extern bool ksu_execveat_hook",
        "execveat extern declarations",
    )
    edit_re(
        "fs/exec.c",
        r"(int flags\)\n\{\n)\n?(\treturn __do_execve_file\(fd, filename, argv, envp, flags, NULL\);)",
        lambda m: m.group(1) + lines(
            "#ifdef CONFIG_KSU",
            "\tif (unlikely(ksu_execveat_hook))",
            "\t\tksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);",
            "\telse",
            "\t\tksu_handle_execveat_sucompat(&fd, &filename, &argv, &envp, &flags);",
            "#endif",
        ).rstrip("\n") + "\n" + m.group(2),
        "ksu_handle_execveat(&fd, &filename, &argv",
        "execveat hook in do_execveat_common",
    )

    # drivers/input/input.c: tolerant to "int disposition = ..." split in two statements
    edit(
        "drivers/input/input.c",
        "static void input_handle_event(struct input_dev *dev,\n",
        lines(
            "#ifdef CONFIG_KSU",
            "extern bool ksu_input_hook __read_mostly;",
            "extern int ksu_handle_input_handle_event(unsigned int *type, unsigned int *code, int *value);",
            "#endif",
            "static void input_handle_event(struct input_dev *dev,",
        ),
        "extern bool ksu_input_hook",
        "input extern declarations",
    )
    edit_re(
        "drivers/input/input.c",
        r"(\n\t(?:int )?disposition = input_get_disposition\(dev, type, code, &value\);\n)\n?(\tif \(disposition != INPUT_IGNORE_EVENT && type != EV_SYN\))",
        lambda m: m.group(1) + "\n" + lines(
            "#ifdef CONFIG_KSU",
            "\tif (unlikely(ksu_input_hook))",
            "\t\tksu_handle_input_handle_event(&type, &code, &value);",
            "#endif",
        ) + m.group(2),
        "ksu_handle_input_handle_event(&type",
        "input_handle_event hook",
    )


EXPECTED_SUSFS_REJ = {
    "./include/linux/mount.h.rej",
    "./fs/proc/cmdline.c.rej",
    "./fs/proc/task_mmu.c.rej",
    "./fs/namespace.c.rej",
}
EXPECTED_HOOKS_REJ = {
    "./fs/exec.c.rej",
    "./drivers/input/input.c.rej",
}

mode = sys.argv[1] if len(sys.argv) > 1 else "susfs"
if mode == "susfs":
    fix_susfs()
    EXPECTED_REJ = EXPECTED_SUSFS_REJ
elif mode == "hooks":
    fix_hooks()
    EXPECTED_REJ = EXPECTED_HOOKS_REJ
else:
    print("unknown mode: %s (use susfs or hooks)" % mode)
    sys.exit(2)

# ------------------------------------------------------- reject cleanup
leftover = []
for root, _dirs, files in os.walk("."):
    if root.startswith("./out") or "/.git" in root:
        continue
    for name in files:
        if name.endswith(".rej"):
            full = os.path.join(root, name)
            if full in EXPECTED_REJ and not FAILED:
                os.remove(full)
                print("[rm]   %s (handled by fixup)" % full)
            else:
                leftover.append(full)

if FAILED or leftover:
    print("")
    print("Fixup (%s) incomplete." % mode)
    for p in FAILED:
        print("  failed edit: %s" % p)
    for p in leftover:
        print("  unhandled reject: %s" % p)
    sys.exit(1)

print("fixup (%s) done." % mode)
