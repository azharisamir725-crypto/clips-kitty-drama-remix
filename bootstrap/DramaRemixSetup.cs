using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace DramaRemixSetup
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new InstallerForm());
        }
    }

    public class InstallerForm : Form
    {
        private readonly Label title = new Label();
        private readonly Label info = new Label();
        private readonly Label installLabel = new Label();
        private readonly TextBox installPath = new TextBox();
        private readonly Button browse = new Button();
        private readonly Label status = new Label();
        private readonly ProgressBar progress = new ProgressBar();
        private readonly Button start = new Button();

        private const string ReleaseBase =
            "https://github.com/azharisamir725-crypto/clips-kitty-drama-remix/releases/download/v0.1.0/";

        private readonly string[] parts = new[]
        {
            "DramaRemix.part01",
            "DramaRemix.part02",
            "DramaRemix.part03",
            "DramaRemix.part04"
        };

        public InstallerForm()
        {
            Text = "短剧二创工具 安装程序";
            Width = 680;
            Height = 390;
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;

            title.Text = "短剧二创工具";
            title.Font = new Font("Microsoft YaHei UI", 18, FontStyle.Bold);
            title.AutoSize = true;
            title.Left = 28;
            title.Top = 24;

            info.Text =
                "安装程序会下载约 6.7GB 的完整短剧版组件。\r\n" +
                "下载缓存、合并和解压都会放在你选择的磁盘，不会把大文件塞进 C 盘。";
            info.Font = new Font("Microsoft YaHei UI", 10);
            info.AutoSize = true;
            info.Left = 30;
            info.Top = 72;

            installLabel.Text = "安装位置：";
            installLabel.Font = new Font("Microsoft YaHei UI", 9);
            installLabel.AutoSize = true;
            installLabel.Left = 30;
            installLabel.Top = 128;

            installPath.Left = 30;
            installPath.Top = 150;
            installPath.Width = 500;
            installPath.Font = new Font("Microsoft YaHei UI", 9);
            installPath.Text = GetDefaultInstallPath();

            browse.Text = "选择位置…";
            browse.Left = 540;
            browse.Top = 148;
            browse.Width = 95;
            browse.Height = 28;
            browse.Click += (s, e) => PickInstallFolder();

            status.Text = "准备就绪";
            status.Font = new Font("Microsoft YaHei UI", 9);
            status.AutoSize = false;
            status.Width = 605;
            status.Left = 30;
            status.Top = 205;

            progress.Left = 30;
            progress.Top = 232;
            progress.Width = 605;
            progress.Height = 22;
            progress.Minimum = 0;
            progress.Maximum = 100;

            start.Text = "开始安装";
            start.Font = new Font("Microsoft YaHei UI", 10, FontStyle.Bold);
            start.Width = 130;
            start.Height = 38;
            start.Left = 505;
            start.Top = 282;
            start.Click += async (s, e) => await InstallAsync();

            Controls.Add(title);
            Controls.Add(info);
            Controls.Add(installLabel);
            Controls.Add(installPath);
            Controls.Add(browse);
            Controls.Add(status);
            Controls.Add(progress);
            Controls.Add(start);
        }

        private static string GetDefaultInstallPath()
        {
            try
            {
                var windowsRoot = Path.GetPathRoot(
                    Environment.GetFolderPath(Environment.SpecialFolder.Windows)
                );

                var drive = DriveInfo.GetDrives()
                    .Where(d => d.IsReady && d.DriveType == DriveType.Fixed)
                    .Where(d => !string.Equals(
                        d.RootDirectory.FullName,
                        windowsRoot,
                        StringComparison.OrdinalIgnoreCase
                    ))
                    .OrderByDescending(d => d.AvailableFreeSpace)
                    .FirstOrDefault();

                if (drive != null)
                    return Path.Combine(drive.RootDirectory.FullName, "DramaRemix");
            }
            catch { }

            return Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs",
                "DramaRemix"
            );
        }

        private void PickInstallFolder()
        {
            using (var dialog = new FolderBrowserDialog())
            {
                dialog.Description = "选择短剧二创工具要安装到哪个磁盘或文件夹";
                dialog.ShowNewFolderButton = true;

                try
                {
                    var current = installPath.Text.Trim();
                    var parent = Directory.GetParent(current);
                    if (parent != null && Directory.Exists(parent.FullName))
                        dialog.SelectedPath = parent.FullName;
                }
                catch { }

                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    var selected = dialog.SelectedPath;
                    if (string.Equals(
                        Path.GetFileName(selected.TrimEnd(Path.DirectorySeparatorChar)),
                        "DramaRemix",
                        StringComparison.OrdinalIgnoreCase
                    ))
                    {
                        installPath.Text = selected;
                    }
                    else
                    {
                        installPath.Text = Path.Combine(selected, "DramaRemix");
                    }
                }
            }
        }

        private async Task InstallAsync()
        {
            start.Enabled = false;
            browse.Enabled = false;
            installPath.Enabled = false;

            string temp = null;
            try
            {
                var installDir = Path.GetFullPath(installPath.Text.Trim());
                if (string.IsNullOrWhiteSpace(installDir))
                    throw new InvalidOperationException("请选择安装位置。");

                var root = Path.GetPathRoot(installDir);
                if (string.Equals(
                    installDir.TrimEnd(Path.DirectorySeparatorChar),
                    root == null ? "" : root.TrimEnd(Path.DirectorySeparatorChar),
                    StringComparison.OrdinalIgnoreCase
                ))
                    throw new InvalidOperationException("不能直接安装到磁盘根目录，请选择一个文件夹。");

                var drive = new DriveInfo(root);
                const long required = 18L * 1024L * 1024L * 1024L;
                if (drive.IsReady && drive.AvailableFreeSpace < required)
                {
                    throw new IOException(
                        "所选磁盘可用空间不足。建议至少预留 18GB，再重新安装。"
                    );
                }

                // Clean any partial files created by the first installer on C:.
                try
                {
                    var legacyTemp = Path.Combine(Path.GetTempPath(), "DramaRemixSetup");
                    if (Directory.Exists(legacyTemp))
                        Directory.Delete(legacyTemp, true);
                }
                catch { }

                var parentDir = Directory.GetParent(installDir);
                if (parentDir == null)
                    throw new InvalidOperationException("安装位置无效，请重新选择。");

                Directory.CreateDirectory(parentDir.FullName);
                temp = Path.Combine(parentDir.FullName, ".DramaRemixSetupTemp");

                if (Directory.Exists(temp))
                    Directory.Delete(temp, true);
                Directory.CreateDirectory(temp);

                var zipPath = Path.Combine(temp, "DramaRemix.zip");

                using (var combined = new FileStream(
                    zipPath,
                    FileMode.Create,
                    FileAccess.Write,
                    FileShare.None,
                    1024 * 1024,
                    true
                ))
                using (var http = new HttpClient(new HttpClientHandler { AllowAutoRedirect = true }))
                {
                    http.DefaultRequestHeaders.UserAgent.ParseAdd("DramaRemixSetup/0.2");

                    for (int i = 0; i < parts.Length; i++)
                    {
                        var name = parts[i];
                        var url = ReleaseBase + name;
                        status.Text = string.Format(
                            "正在下载 {0}/{1}：{2}",
                            i + 1,
                            parts.Length,
                            name
                        );

                        using (var response = await http.GetAsync(
                            url,
                            HttpCompletionOption.ResponseHeadersRead
                        ))
                        {
                            response.EnsureSuccessStatusCode();
                            var length = response.Content.Headers.ContentLength ?? 0;

                            using (var input = await response.Content.ReadAsStreamAsync())
                            {
                                var buffer = new byte[1024 * 1024];
                                long readTotal = 0;

                                while (true)
                                {
                                    var read = await input.ReadAsync(buffer, 0, buffer.Length);
                                    if (read <= 0)
                                        break;

                                    await combined.WriteAsync(buffer, 0, read);
                                    readTotal += read;

                                    var within = length > 0
                                        ? (double)readTotal / length
                                        : 0;

                                    var overall = ((double)i + within) / parts.Length;
                                    progress.Value = Math.Max(
                                        0,
                                        Math.Min(78, (int)(overall * 78))
                                    );
                                }
                            }
                        }
                    }
                }

                status.Text = "下载完成，正在准备解压…";
                progress.Value = 82;

                if (Directory.Exists(installDir))
                    Directory.Delete(installDir, true);
                Directory.CreateDirectory(installDir);

                status.Text = "正在解压完整程序，这一步需要几分钟…";
                progress.Value = 86;
                ZipFile.ExtractToDirectory(zipPath, installDir);
                progress.Value = 96;

                var exe = Directory.GetFiles(
                    installDir,
                    "Clips Kitty.exe",
                    SearchOption.AllDirectories
                ).FirstOrDefault();

                if (exe == null)
                    throw new FileNotFoundException(
                        "安装完成后没有找到程序主文件 Clips Kitty.exe"
                    );

                status.Text = "正在创建桌面快捷方式…";
                CreateShortcut(exe);
                progress.Value = 100;
                status.Text = "安装完成，正在启动短剧二创工具。";

                try
                {
                    Process.Start(new ProcessStartInfo(exe) { UseShellExecute = true });
                }
                catch { }

                try
                {
                    if (Directory.Exists(temp))
                        Directory.Delete(temp, true);
                }
                catch { }

                MessageBox.Show(
                    "安装完成。\r\n\r\n安装位置：" + installDir +
                    "\r\n桌面已经创建“短剧二创工具”快捷方式。",
                    "短剧二创工具",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information
                );
                Close();
            }
            catch (Exception ex)
            {
                start.Enabled = true;
                browse.Enabled = true;
                installPath.Enabled = true;
                status.Text = "安装失败：" + ex.Message;

                MessageBox.Show(
                    "安装失败：\r\n\r\n" + ex.Message,
                    "短剧二创工具",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
            }
        }

        private static void CreateShortcut(string exe)
        {
            var desktop = Environment.GetFolderPath(
                Environment.SpecialFolder.DesktopDirectory
            );
            var link = Path.Combine(desktop, "短剧二创工具.lnk");

            var shellType = Type.GetTypeFromProgID("WScript.Shell");
            if (shellType == null)
                return;

            object shellObj = null;
            object shortcutObj = null;

            try
            {
                shellObj = Activator.CreateInstance(shellType);
                dynamic shell = shellObj;
                shortcutObj = shell.CreateShortcut(link);
                dynamic shortcut = shortcutObj;
                shortcut.TargetPath = exe;
                shortcut.WorkingDirectory = Path.GetDirectoryName(exe);
                shortcut.Description = "短剧一键二创工具";
                shortcut.Save();
            }
            finally
            {
                if (shortcutObj != null && Marshal.IsComObject(shortcutObj))
                    Marshal.FinalReleaseComObject(shortcutObj);

                if (shellObj != null && Marshal.IsComObject(shellObj))
                    Marshal.FinalReleaseComObject(shellObj);
            }
        }
    }
}
