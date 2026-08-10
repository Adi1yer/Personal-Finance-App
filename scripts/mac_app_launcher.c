/*
 * Native stub for Personal Finance.app (CFBundleExecutable).
 * Finder/LaunchServices need a Mach-O binary — a shell script as the
 * executable often fails silently or only works when opened in Terminal.
 */
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/sysctl.h>
#include <unistd.h>

static void trim_newline(char *s) {
  size_t n = strlen(s);
  while (n > 0 && (s[n - 1] == '\n' || s[n - 1] == '\r' || s[n - 1] == ' ')) {
    s[--n] = '\0';
  }
}

static void alert(const char *message) {
  /* Keep message free of double-quotes; used only for our fixed strings. */
  char cmd[2048];
  snprintf(
      cmd,
      sizeof(cmd),
      "osascript -e 'display alert \"Personal Finance\" message \"%s\" as critical' >/dev/null 2>&1",
      message);
  system(cmd);
}

static void open_log(void) {
  const char *home = getenv("HOME");
  if (!home || !home[0]) {
    return;
  }
  char dir[PATH_MAX];
  char path[PATH_MAX];
  snprintf(dir, sizeof(dir), "%s/Library/Application Support/PersonalFinance/logs", home);
  snprintf(path, sizeof(path), "%s/app-launch.log", dir);
  char mkdir_cmd[PATH_MAX + 32];
  snprintf(mkdir_cmd, sizeof(mkdir_cmd), "/bin/mkdir -p \"%s\"", dir);
  system(mkdir_cmd);
  FILE *f = freopen(path, "a", stderr);
  if (f) {
    fprintf(stderr, "\n--- app launch ---\n");
    fflush(stderr);
  }
}

static int read_project_root(char *out, size_t out_sz) {
  char exe[PATH_MAX];
  uint32_t size = sizeof(exe);
  if (_NSGetExecutablePath(exe, &size) != 0) {
    return -1;
  }
  char resolved[PATH_MAX];
  if (!realpath(exe, resolved)) {
    strncpy(resolved, exe, sizeof(resolved) - 1);
    resolved[sizeof(resolved) - 1] = '\0';
  }

  /* .../App.app/Contents/MacOS/<exe> → .../Contents/Resources/project_root */
  char *slash = strrchr(resolved, '/');
  if (!slash) {
    return -1;
  }
  *slash = '\0'; /* MacOS */

  char root_file[PATH_MAX];
  snprintf(root_file, sizeof(root_file), "%s/../Resources/project_root", resolved);

  FILE *f = fopen(root_file, "r");
  if (!f) {
    return -1;
  }
  if (!fgets(out, (int)out_sz, f)) {
    fclose(f);
    return -1;
  }
  fclose(f);
  trim_newline(out);
  return out[0] ? 0 : -1;
}

static int is_apple_silicon(void) {
  int value = 0;
  size_t len = sizeof(value);
  if (sysctlbyname("hw.optional.arm64", &value, &len, NULL, 0) != 0) {
    return 0;
  }
  return value == 1;
}

int main(int argc, char **argv) {
  (void)argc;
  (void)argv;
  open_log();

  char root[PATH_MAX];
  if (read_project_root(root, sizeof(root)) != 0) {
    fprintf(stderr, "missing Resources/project_root\n");
    alert("Could not find the project folder. From your clone, run: make mac-app");
    return 1;
  }

  char launch_sh[PATH_MAX];
  snprintf(launch_sh, sizeof(launch_sh), "%s/scripts/launch.sh", root);
  struct stat st;
  if (stat(launch_sh, &st) != 0 || !S_ISREG(st.st_mode)) {
    fprintf(stderr, "missing launch.sh under %s\n", root);
    alert("Project folder is missing or was moved. Re-run make mac-app from your clone.");
    return 1;
  }

  if (setenv("PERSONAL_FINANCE_ROOT", root, 1) != 0) {
    alert("Failed to set PERSONAL_FINANCE_ROOT.");
    return 1;
  }

  const char *path = getenv("PATH");
  char new_path[PATH_MAX * 2];
  snprintf(
      new_path,
      sizeof(new_path),
      "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin%s%s",
      (path && path[0]) ? ":" : "",
      (path && path[0]) ? path : "");
  setenv("PATH", new_path, 1);

  fprintf(stderr, "PERSONAL_FINANCE_ROOT=%s\n", root);
  fflush(stderr);

  /* Finder may start the .app under Rosetta; force arm64 bash on Apple Silicon. */
  if (is_apple_silicon()) {
    execl("/usr/bin/arch", "arch", "-arm64", "/bin/bash", launch_sh, (char *)NULL);
  }
  execl("/bin/bash", "bash", launch_sh, (char *)NULL);

  fprintf(stderr, "exec failed\n");
  alert("Failed to start Personal Finance. See logs in Application Support/PersonalFinance/logs.");
  return 1;
}
