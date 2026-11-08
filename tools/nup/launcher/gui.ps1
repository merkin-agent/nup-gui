Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text = 'NUP Packager'
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.ClientSize = New-Object System.Drawing.Size(760, 220)

$labelSource = New-Object System.Windows.Forms.Label
$labelSource.Text = 'Dump parent folder'
$labelSource.Location = New-Object System.Drawing.Point(16, 22)
$labelSource.Size = New-Object System.Drawing.Size(130, 24)
$form.Controls.Add($labelSource)

$source = New-Object System.Windows.Forms.TextBox
$source.Location = New-Object System.Drawing.Point(150, 18)
$source.Size = New-Object System.Drawing.Size(480, 26)
$form.Controls.Add($source)

$browseSource = New-Object System.Windows.Forms.Button
$browseSource.Text = 'Browse...'
$browseSource.Location = New-Object System.Drawing.Point(640, 16)
$browseSource.Size = New-Object System.Drawing.Size(100, 30)
$browseSource.Add_Click({
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = 'Choose the folder containing base/, updates/, dlc/, or content folders'
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $source.Text = $dialog.SelectedPath
        if (-not $output.Text) {
            $parent = [System.IO.Directory]::GetParent($dialog.SelectedPath).FullName
            $leaf = [System.IO.Path]::GetFileName($dialog.SelectedPath.TrimEnd('\'))
            $output.Text = [System.IO.Path]::Combine($parent, $leaf + '.nup')
        }
    }
})
$form.Controls.Add($browseSource)

$labelOutput = New-Object System.Windows.Forms.Label
$labelOutput.Text = 'Output .nup file'
$labelOutput.Location = New-Object System.Drawing.Point(16, 66)
$labelOutput.Size = New-Object System.Drawing.Size(130, 24)
$form.Controls.Add($labelOutput)

$output = New-Object System.Windows.Forms.TextBox
$output.Location = New-Object System.Drawing.Point(150, 62)
$output.Size = New-Object System.Drawing.Size(480, 26)
$form.Controls.Add($output)

$browseOutput = New-Object System.Windows.Forms.Button
$browseOutput.Text = 'Browse...'
$browseOutput.Location = New-Object System.Drawing.Point(640, 60)
$browseOutput.Size = New-Object System.Drawing.Size(100, 30)
$browseOutput.Add_Click({
    $dialog = New-Object System.Windows.Forms.SaveFileDialog
    $dialog.Title = 'Save NUP package'
    $dialog.DefaultExt = 'nup'
    $dialog.AddExtension = $true
    $dialog.Filter = 'NUP package (*.nup)|*.nup|All files (*.*)|*.*'
    if ($output.Text) { $dialog.FileName = $output.Text }
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $output.Text = $dialog.FileName
    }
})
$form.Controls.Add($browseOutput)

$status = New-Object System.Windows.Forms.Label
$status.Text = 'Choose the dump folder and output file.'
$status.Location = New-Object System.Drawing.Point(16, 112)
$status.Size = New-Object System.Drawing.Size(720, 24)
$form.Controls.Add($status)

$progress = New-Object System.Windows.Forms.ProgressBar
$progress.Location = New-Object System.Drawing.Point(16, 143)
$progress.Size = New-Object System.Drawing.Size(724, 18)
$progress.Style = 'Marquee'
$progress.MarqueeAnimationSpeed = 25
$progress.Visible = $false
$form.Controls.Add($progress)

$start = New-Object System.Windows.Forms.Button
$start.Text = 'Create NUP'
$start.Location = New-Object System.Drawing.Point(620, 174)
$start.Size = New-Object System.Drawing.Size(120, 32)
$form.Controls.Add($start)

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 250
$script:packProcess = $null
$timer.Add_Tick({
    if ($script:packProcess -and $script:packProcess.HasExited) {
        $timer.Stop()
        $code = $script:packProcess.ExitCode
        $script:packProcess.Dispose()
        $script:packProcess = $null
        $progress.Visible = $false
        $start.Enabled = $true
        if ($code -eq 0) {
            $status.Text = 'Package created successfully.'
            [System.Windows.Forms.MessageBox]::Show("Created:`n$($output.Text)", 'NUP created', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null
        } else {
            $status.Text = "Packing failed (exit code $code)."
            [System.Windows.Forms.MessageBox]::Show("The packer exited with code $code. Check the dump layout and try again.", 'Packing failed', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
        }
    }
})

$start.Add_Click({
    if (-not $source.Text -or -not [System.IO.Directory]::Exists($source.Text)) {
        [System.Windows.Forms.MessageBox]::Show('Choose an existing dump parent folder.', 'Folder required', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
        return
    }
    if (-not $output.Text) {
        [System.Windows.Forms.MessageBox]::Show('Choose where to save the .nup file.', 'Output required', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
        return
    }
    if ([System.IO.File]::Exists($output.Text)) {
        [System.Windows.Forms.MessageBox]::Show('Choose a new output filename. Existing NUP files are not overwritten.', 'File already exists', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
        return
    }

    $arguments = 'pack "' + $source.Text + '" "' + $output.Text + '"'
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $env:NUP_CLI_PATH
    $info.Arguments = $arguments
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $script:packProcess = New-Object System.Diagnostics.Process
    $script:packProcess.StartInfo = $info
    try {
        [void]$script:packProcess.Start()
        $start.Enabled = $false
        $progress.Visible = $true
        $status.Text = 'Packing dump contents. Large dumps may take a while...'
        $timer.Start()
    } catch {
        $script:packProcess.Dispose()
        $script:packProcess = $null
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Could not start packer', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    }
})

[void]$form.ShowDialog()
