# Generates icon.ico (32x32) in the SalesPlan folder.
# Run once alongside install_shortcut.ps1

Add-Type -AssemblyName System.Drawing

$size = 32
$bmp  = New-Object System.Drawing.Bitmap($size, $size)
$g    = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

# Background — brand blue rounded rect
$bg = [System.Drawing.Color]::FromArgb(255, 27, 79, 138)   # #1B4F8A
$brush = New-Object System.Drawing.SolidBrush($bg)
$g.FillRectangle($brush, 0, 0, $size, $size)

# "S" letterform — white
$font  = New-Object System.Drawing.Font("Segoe UI", 18, [System.Drawing.FontStyle]::Bold)
$white = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
$sf    = New-Object System.Drawing.StringFormat
$sf.Alignment     = [System.Drawing.StringAlignment]::Center
$sf.LineAlignment = [System.Drawing.StringAlignment]::Center
$rect  = New-Object System.Drawing.RectangleF(0, 0, $size, $size)
$g.DrawString("S", $font, $white, $rect, $sf)

# Accent dot — #00A86B green
$accentBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 0, 168, 107))
$g.FillEllipse($accentBrush, 20, 20, 9, 9)

$g.Dispose()

# Save as ICO (single 32x32 frame via raw ICO header)
$icoPath = "$PSScriptRoot\icon.ico"
$ms      = New-Object System.IO.MemoryStream

# PNG-encode the bitmap into a temp stream
$pngMs = New-Object System.IO.MemoryStream
$bmp.Save($pngMs, [System.Drawing.Imaging.ImageFormat]::Png)
$pngBytes = $pngMs.ToArray()

$writer = New-Object System.IO.BinaryWriter($ms)

# ICO file header
$writer.Write([UInt16]0)       # reserved
$writer.Write([UInt16]1)       # type = ICO
$writer.Write([UInt16]1)       # image count

# Image directory entry
$writer.Write([Byte]32)        # width
$writer.Write([Byte]32)        # height
$writer.Write([Byte]0)         # colour count (0 = >256)
$writer.Write([Byte]0)         # reserved
$writer.Write([UInt16]1)       # colour planes
$writer.Write([UInt16]32)      # bits per pixel
$writer.Write([UInt32]$pngBytes.Length)   # size of image data
$writer.Write([UInt32]22)      # offset of image data (6 header + 16 dir)

$writer.Write($pngBytes)
$writer.Flush()

[System.IO.File]::WriteAllBytes($icoPath, $ms.ToArray())
$bmp.Dispose()

Write-Host "  icon.ico created at $icoPath" -ForegroundColor Green
