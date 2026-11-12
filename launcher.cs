using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class Launcher {
    [STAThread]
    static void Main(string[] args) {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, "runtime", "pythonw.exe");
        if (!File.Exists(python)) python = Path.Combine(root, ".venv", "Scripts", "pythonw.exe");
        string script = Path.Combine(root, "app.py");
        if (!File.Exists(python) || !File.Exists(script)) {
            MessageBox.Show("运行文件不完整，请保留 PdfSizeOPT 文件夹中的 runtime、src 和 app.py。", "PdfSizeOPT");
            return;
        }
        string quoted = "-s \"" + script + "\"";
        foreach (string arg in args) {
            // Windows file paths cannot contain quote characters.
            if (arg.IndexOf('"') < 0) quoted += " \"" + arg.TrimEnd('\\') + "\"";
        }
        try {
            var info = new ProcessStartInfo(python, quoted);
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.EnvironmentVariables["PYTHONUTF8"] = "1";
            info.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
            Process.Start(info);
        } catch (Exception ex) {
            MessageBox.Show(ex.Message, "PdfSizeOPT 启动失败");
        }
    }
}
