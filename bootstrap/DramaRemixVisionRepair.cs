using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace DramaRemixVisionRepair
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new RepairForm());
        }
    }

    public class RepairForm : Form
    {
        private readonly Label title = new Label();
        private readonly Label info = new Label();
        private readonly Label status = new Label();
        private readonly ProgressBar progress = new ProgressBar();
        private readonly Button start = new Button();

        private const string HotfixUrl =
            "https://github.com/azharisamir725-crypto/clips-kitty-drama-remix/releases/download/v0.1.0/vision-hotfix.zip";

        public RepairForm()
        {
            Text = "短剧二创工具 修复程序";
            Width = 610;
            Height = 280;
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;

            title.Text = "TorchVision 修复";
            title.Font = new System.Drawing.Font("Microsoft YaHei UI", 18, System.Drawing.FontStyle.Bold);
            title.AutoSize = true;
            title.Left = 28;
            title.Top = 24;

            info.Text =
                "用于修复：operator torchvision::nms does not exist\r\n" +
                "不需要重新下载 6.7GB 完整程序。";
            info.Font = new System.Drawing.Font("Microsoft YaHei UI", 10);
            info.AutoSize = true;
            info.Left = 30;
            info.Top = 72;

            status.Text = "请先关闭短剧二创工具，然后点击开始修复。";
            status.Font = new System.Drawing.Font("Microsoft YaHei UI", 9);
            status.AutoSize = false;
            status.Width = 535;
            status.Left = 30;
            status.Top = 130;

            progress.Left = 30;
            progress.Top = 160;
            progress.Width = 535;
            progress.Height = 22;
            progress.Minimum = 0;
            progress.Maximum = 100;

            start.Text = "开始修复";
            start.Font = new System.Drawing.Font("Microsoft YaHei UI", 10, System.Drawing.FontStyle.Bold);
            start.Width = 120;
            start.Height = 36;
            start.Left = 445;
            start.Top = 195;
            start.Click += async (s, e) => await RepairAsync();

            Controls.Add(title);
            Controls.Add(info);
            Controls.Add(status);
            Controls.Add(progress);
            Controls.Add(start);
        }

        private async Task RepairAsync()
        {
            start.Enabled = false;
            try
            {
                status.Text = "正在关闭正在运行的 Clips Kitty…";
                progress.Value = 5;
                foreach (var p in Process.GetProcesses())
                {
                    try
                    {
                        if (string.Equals(p.ProcessName, "Clips Kitty", StringComparison.OrdinalIgnoreCase))
                        {
                            p.Kill();
                            p.WaitForExit(5000);
                        }
                    }
                    catch { }
                    finally { p.Dispose(); }
                }

                var exe = ResolveInstalledExe();
                if (string.IsNullOrWhiteSpace(exe) || !File.Exists(exe))
                    throw new FileNotFoundException("没有找到已安装的短剧二创工具，请确认桌面有“短剧二创工具”快捷方式。");

                var appDir = Path.GetDirectoryName(exe);
                var backend = Path.Combine(appDir, "resources", "backend");
                if (!Directory.Exists(backend))
                {
                    var api = Directory.GetFiles(appDir, "api.exe", SearchOption.AllDirectories).FirstOrDefault();
                    if (api == null)
                        throw new DirectoryNotFoundException("没有找到程序后端目录。");
                    backend = Path.GetDirectoryName(api);
                }

                var tvDir = Path.Combine(backend, "_internal", "torchvision");
                Directory.CreateDirectory(tvDir);

                var temp = Path.Combine(Path.GetTempPath(), "DramaRemixVisionRepair");
                if (Directory.Exists(temp)) Directory.Delete(temp, true);
                Directory.CreateDirectory(temp);
                var zip = Path.Combine(temp, "vision-hotfix.zip");

                status.Text = "正在下载修复文件…";
                progress.Value = 20;
                using (var http = new HttpClient(new HttpClientHandler { AllowAutoRedirect = true }))
                {
                    http.DefaultRequestHeaders.UserAgent.ParseAdd("DramaRemixVisionRepair/0.1");
                    var bytes = await http.GetByteArrayAsync(HotfixUrl);
                    File.WriteAllBytes(zip, bytes);
                }

                status.Text = "正在安装 TorchVision 原生组件…";
                progress.Value = 55;
                var extracted = Path.Combine(temp, "files");
                ZipFile.ExtractToDirectory(zip, extracted);

                var nativeFiles = Directory.GetFiles(extracted, "*.*", SearchOption.AllDirectories)
                    .Where(p => p.EndsWith(".pyd", StringComparison.OrdinalIgnoreCase)
                             || p.EndsWith(".dll", StringComparison.OrdinalIgnoreCase))
                    .ToArray();

                if (nativeFiles.Length == 0)
                    throw new InvalidDataException("修复包里没有找到原生组件。");

                foreach (var src in nativeFiles)
                {
                    var dst = Path.Combine(tvDir, Path.GetFileName(src));
                    File.Copy(src, dst, true);
                }

                progress.Value = 100;
                status.Text = "修复完成，正在重新打开短剧二创工具。";

                try { Directory.Delete(temp, true); } catch { }

                try
                {
                    Process.Start(new ProcessStartInfo(exe) { UseShellExecute = true });
                }
                catch { }

                MessageBox.Show(
                    "修复完成。\r\n\r\n请回到“短剧二创”，重新提交刚才的视频任务，不要点旧失败任务的 Retry。",
                    "短剧二创工具",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information
                );
                Close();
            }
            catch (Exception ex)
            {
                start.Enabled = true;
                status.Text = "修复失败：" + ex.Message;
                MessageBox.Show(
                    "修复失败：\r\n\r\n" + ex.Message,
                    "短剧二创工具",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
            }
        }

        private static string ResolveInstalledExe()
        {
            var desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            var link = Path.Combine(desktop, "短剧二创工具.lnk");
            if (!File.Exists(link)) return null;

            var shellType = Type.GetTypeFromProgID("WScript.Shell");
            if (shellType == null) return null;

            object shellObj = null;
            object shortcutObj = null;
            try
            {
                shellObj = Activator.CreateInstance(shellType);
                dynamic shell = shellObj;
                shortcutObj = shell.CreateShortcut(link);
                dynamic shortcut = shortcutObj;
                return Convert.ToString(shortcut.TargetPath);
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
