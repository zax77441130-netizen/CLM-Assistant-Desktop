$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$Form = [System.Windows.Forms.Form]::new()
$Form.Text = "CLM Phase 6 UIA Fixture"
$Form.Name = "ClmPhase6Fixture"
$Form.Width = 520
$Form.Height = 360
$Form.StartPosition = "CenterScreen"
$Form.MinimizeBox = $true
$Form.MaximizeBox = $true

$TextBox = [System.Windows.Forms.TextBox]::new()
$TextBox.Name = "GeneralTextBox"
$TextBox.AccessibleName = "General text"
$TextBox.Left = 20
$TextBox.Top = 20
$TextBox.Width = 460
$TextBox.Height = 28

$PasswordBox = [System.Windows.Forms.TextBox]::new()
$PasswordBox.Name = "PasswordTextBox"
$PasswordBox.AccessibleName = "Password"
$PasswordBox.UseSystemPasswordChar = $true
$PasswordBox.Left = 20
$PasswordBox.Top = 60
$PasswordBox.Width = 460
$PasswordBox.Height = 28

$ListBox = [System.Windows.Forms.ListBox]::new()
$ListBox.Name = "SampleList"
$ListBox.AccessibleName = "Sample list"
$ListBox.Left = 20
$ListBox.Top = 100
$ListBox.Width = 220
$ListBox.Height = 100
[void]$ListBox.Items.Add("Alpha")
[void]$ListBox.Items.Add("Beta")
[void]$ListBox.Items.Add("Gamma")

$StatusLabel = [System.Windows.Forms.Label]::new()
$StatusLabel.Name = "StatusText"
$StatusLabel.AccessibleName = "Status"
$StatusLabel.Left = 20
$StatusLabel.Top = 220
$StatusLabel.Width = 460
$StatusLabel.Height = 28
$StatusLabel.Text = "Ready"

$SafeButton = [System.Windows.Forms.Button]::new()
$SafeButton.Name = "SafeButton"
$SafeButton.AccessibleName = "Run"
$SafeButton.Left = 260
$SafeButton.Top = 100
$SafeButton.Width = 100
$SafeButton.Height = 34
$SafeButton.Text = "Run"
$SafeButton.Add_Click({ $StatusLabel.Text = "Safe button invoked" })

$DangerButton = [System.Windows.Forms.Button]::new()
$DangerButton.Name = "DangerButton"
$DangerButton.AccessibleName = "Delete"
$DangerButton.Left = 380
$DangerButton.Top = 100
$DangerButton.Width = 100
$DangerButton.Height = 34
$DangerButton.Text = "Delete"
$DangerButton.Add_Click({ $StatusLabel.Text = "Danger button invoked" })

$CloseButton = [System.Windows.Forms.Button]::new()
$CloseButton.Name = "CloseButton"
$CloseButton.AccessibleName = "Close"
$CloseButton.Left = 380
$CloseButton.Top = 170
$CloseButton.Width = 100
$CloseButton.Height = 34
$CloseButton.Text = "Close"
$CloseButton.Add_Click({ $Form.Close() })

$Form.Controls.AddRange(@($TextBox, $PasswordBox, $ListBox, $StatusLabel, $SafeButton, $DangerButton, $CloseButton))
[void]$Form.ShowDialog()
