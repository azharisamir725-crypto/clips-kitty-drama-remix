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
            Width = 620;
            Height = 310;
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;

            title.Text = "短剧二创工具";
            title.Font = new Font("Microsoft YaHei UI", 18, FontStyle.Bold);
            title.AutoSize = true;
            title.Left = 28;
            title.Top = 25;

            info.Text =
                "安装程序会下载约 6.7GB 的完整短剧版组件。\r\n" +
                "安装位置：当前 Windows 用户目录，不会覆盖你原来的 Clips Kitty。";
            info.Font = new Font("Microsoft YaHei UI", 10);
            info.AutoSize = true;
            info.Left = 30;
            info.Top = 75;

            status.Text = "准备就绪";
            status.Font = new Font("Microsoft YaHei UI", 9);
            status.AutoSize = false;
            status.Width = 540;
            status.Left = 30;
            status.Top = 140;

            progress.Left = 30;
            progress.Top = 170;
            progress.Width = 540;
            progress.Height = 22;
            progress.Minimum = 0;
            progress.Maximum = 100;

            start.Text = "开始安装";
            start.Font = new Font("Microsoft YaHei UI", 10, FontStyle.Bold);
            start.Width = 130;
            start.Height = 38;
            start.Left = 440;
            start.Top = 210;
            start.Click += async (s, e) => await InstallAsync();

            Controls.Add(title);
            Controls.Add(info);
            Controls.Add(status);
            Controls.Add(progress);
            Controls.Add(start);
        }

        private async Task InstallAsync()
        {
            start.Enabled = false;
            try
            {
                var temp = Path.Combine(Path.GetTempPath(), "DramaRemixSetup");
                var installDir = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "Programs",
                    "DramaRemix"
                );

                if (Directory.Exists(temp))
                    Directory.Delete(temp, true);
                Directory.CreateDirectory(temp);

                using (var http = new HttpClient(new HttpClientHandler { AllowAutoRedirect = true }))
                {
                    http.DefaultRequestHeaders.UserAgent.ParseAdd("DramaRemixSetup/0.1");

                    for (int i = 0; i < parts.Length; i++)
                    {
                        var name = parts[i];
                        var url = ReleaseBase + name;
                        var dest = Path.Combine(temp, name);
                        status.Text = string.Format("正在下载 {0}/{1}：{2}", i + 1, parts.Length, name);

                        using (var response = await http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead))
                        {
                            response.EnsureSuccessStatusCode();
                            var length = response.Content.Headers.ContentLength ?? 0;
                            using (var input = await response.Content.ReadAsStreamAsync())
                            using (var output = new FileStream(dest, FileMode.Create, FileAccess.Write, FileShare.None, 1024 * 1024, true))
                            {
                                var buffer = new byte[1024 * 1024];
                                long readTotal = 0;
                                while (true)
                                {
                                    var read = await input.ReadAsync(buffer, 0, buffer.Length);
                                    if (read <= 0) break;
                                    await output.WriteAsync(buffer, 0, read);
                                    readTotal += read;

                                    var within = length > 0 ? (double)readTotal / length : 0;
                                    var overall = ((double)i + within) / parts.Length;
                                    progress.Value = Math.Max(0, Math.Min(78, (int)(overall * 78)));
                                }
                            }
                        }
                    }
                }

                status.Text = "正在合并安装文件…";
                progress.Value = 80;
                var zipPath = Path.Combine(temp, "DramaRemix.zip");
                using (var combined = new FileStream(zipPath, FileMode.Create, FileAccess.Write, FileShare.None))
                {
                    foreach (var name in parts)
                    {
                        using (var piece = new FileStream(Path.Combine(temp, name), FileMode.Open, FileAccess.Read, FileShare.Read))
                            piece.CopyTo(combined, 1024 * 1024);
                    }
                }

                status.Text = "正在解压完整程序，这一步需要几分钟…";
                progress.Value = 86;
                if (Directory.Exists(installDir))
                    Directory.Delete(installDir, true);
                Directory.CreateDirectory(installDir);
                ZipFile.ExtractToDirectory(zipPath, installDir);
                progress.Value = 96;

                var exe = Directory.GetFiles(installDir, "Clips Kitty.exe", SearchOption.AllDirectories).FirstOrDefault();
                if (exe == null)
                    throw new FileNotFoundException("安装完成后没有找到程序主文件 Clips Kitty.exe");

                status.Text = "正在创建桌面快捷方式…";
                CreateShortcut(exe);
                progress.Value = 100;
                status.Text = "安装完成，正在启动短剧二创工具。";

                try
                {
                    Process.Start(new ProcessStartInfo(exe) { UseShellExecute = true });
                }
                catch { }

                try { Directory.Delete(temp, true); } catch { }

                MessageBox.Show(
                    "安装完成。\r\n\r\n桌面已经创建“短剧二创工具”快捷方式。",
                    "短剧二创工具",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information
                );
                Close();
            }
            catch (Exception ex)
            {
                start.Enabled = true;
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
            var desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            var link = Path.Combine(desktop, "短剧二创工具.lnk");

            var shellType = Type.GetTypeFromProgID("WScript.Shell");
            if (shellType == null) return;

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
