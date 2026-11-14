param([string]$OutputDirectory = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$culture = [System.Globalization.CultureInfo]::InvariantCulture
$design = Get-Content -Raw (Join-Path $PSScriptRoot 'design.json') | ConvertFrom-Json
$fontFamily = New-Object System.Drawing.FontFamily('Arial')
$outDir = [System.IO.Path]::GetFullPath($OutputDirectory)
[System.IO.Directory]::CreateDirectory($outDir) | Out-Null
function Num([double]$value) { $value.ToString('0.#####', $culture) }
function OutlinedText([string]$text, [double]$height, [double]$x, [double]$y,
                      [double]$angle, [double]$outerRadius, [bool]$radial) {
    $raw = New-Object System.Drawing.Drawing2D.GraphicsPath
    $raw.AddString($text, $fontFamily, [int][System.Drawing.FontStyle]::Bold, 1000,
        [System.Drawing.PointF]::new(0, 0), [System.Drawing.StringFormat]::GenericTypographic)
    $box = $raw.GetBounds()
    $factor = $height / $box.Height
    $radians = $angle * [Math]::PI / 180
    $ux = [Math]::Sin($radians); $uy = -[Math]::Cos($radians)
    $vx = [Math]::Cos($radians); $vy = [Math]::Sin($radians)
    $points = New-Object 'System.Drawing.PointF[]' $raw.PointCount
    $original = $raw.PathPoints
    for ($i = 0; $i -lt $points.Length; $i++) {
        $localY = ($original[$i].Y - $box.Top - $box.Height/2) * $factor
        if ($radial) {
            $localX = ($original[$i].X - $box.Right) * $factor + $outerRadius
            $points[$i] = [System.Drawing.PointF]::new(
                ($x + $ux*$localX + $vx*$localY), ($y + $uy*$localX + $vy*$localY))
        } else {
            $localX = ($original[$i].X - $box.Left - $box.Width/2) * $factor
            $points[$i] = [System.Drawing.PointF]::new(($x+$localX), ($y+$localY))
        }
    }
    $outlined = [System.Drawing.Drawing2D.GraphicsPath]::new($points, $raw.PathTypes)
    $raw.Dispose()
    return ,$outlined
}
function SvgPath($path) {
    $pieces = [System.Collections.Generic.List[string]]::new()
    $points = $path.PathPoints; $types = $path.PathTypes
    for ($i = 0; $i -lt $points.Length; $i++) {
        $kind = $types[$i] -band 7
        if ($kind -eq 0) {
            $pieces.Add('M' + (Num $points[$i].X) + ',' + (Num $points[$i].Y))
        } elseif ($kind -eq 1) {
            $pieces.Add('L' + (Num $points[$i].X) + ',' + (Num $points[$i].Y))
        } elseif ($kind -eq 3) {
            if ($i+2 -ge $points.Length -or ($types[$i+1] -band 7) -ne 3 -or ($types[$i+2] -band 7) -ne 3) {
                throw 'Invalid cubic font outline'
            }
            $pieces.Add('C' + (Num $points[$i].X) + ',' + (Num $points[$i].Y) + ' ' +
                (Num $points[$i+1].X) + ',' + (Num $points[$i+1].Y) + ' ' +
                (Num $points[$i+2].X) + ',' + (Num $points[$i+2].Y))
            $i += 2
        } else { throw "Unsupported font path type $kind" }
        if ($types[$i] -band 128) { $pieces.Add('Z') }
    }
    return ($pieces -join ' ')
}
function DrawLabel([string]$name, [string]$centerText, $markings, $values,
                   [double]$capHeight, [string]$basename, [bool]$sectorDividers) {
    if ($markings.Count -ne $values.Count -or $markings.Count -lt 2) { throw 'Scale values missing' }
    $canvas = 21.5; $cx = $canvas/2; $cy = $canvas/2
    $radius = [double]$design.diameter_mm / 2
    $density = 40.0 # enlarged review image, not an actual-size print source
    $bitmap = [System.Drawing.Bitmap]::new([int]($canvas*$density),[int]($canvas*$density))
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.Clear([System.Drawing.Color]::White)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.ScaleTransform($density,$density)
    $cutPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(190,45,45),0.05)
    $paths = [System.Collections.Generic.List[string]]::new()
    $dividers = [System.Collections.Generic.List[string]]::new()
    $details = [System.Collections.Generic.List[object]]::new()
    for ($j = 0; $j -lt $markings.Count; $j++) {
        $fraction = [Math]::Log([double]$values[$j]/[double]$values[0]) /
                    [Math]::Log([double]$values[-1]/[double]$values[0])
        # A rotating face is read at a stationary body index: the desired
        # physical increase direction is opposite the printed scale order.
        if ($design.physical_increase_direction -eq 'clockwise') {
            $fraction = 1.0 - $fraction
        }
        $angle = [double]$design.artwork_angles.start_degrees + [double]$design.artwork_angles.sweep_degrees*$fraction
        $path = OutlinedText ([string]$markings[$j]) $capHeight $cx $cy $angle 6.75 $true
        $paths.Add('<path d="' + (SvgPath $path) + '"/>')
        $graphics.FillPath([System.Drawing.Brushes]::Black,$path)
        $details.Add([ordered]@{mark=[string]$markings[$j];value=[double]$values[$j];angle_clockwise_from_12_degrees=$angle;glyph_cap_height_mm=$capHeight})
        $path.Dispose()
    }
    if ($sectorDividers) {
        for ($j = 0; $j -lt $details.Count-1; $j++) {
        $angle = ($details[$j].angle_clockwise_from_12_degrees + $details[$j+1].angle_clockwise_from_12_degrees)/2
        $rad = $angle*[Math]::PI/180; $ux=[Math]::Sin($rad);$uy=-[Math]::Cos($rad)
        $r1=[double]$design.sector_divider_inner_radius_mm
        $r2=[double]$design.sector_divider_outer_radius_mm
        $x1=$cx+$r1*$ux;$y1=$cy+$r1*$uy;$x2=$cx+$r2*$ux;$y2=$cy+$r2*$uy
        # Closed filled boundaries share the lettering's laser Fill layer.
        # Leave the centered caption clear; these are engraving, not cuts.
        $vx=[Math]::Cos($rad);$vy=[Math]::Sin($rad)
        $halfWidth=[double]$design.sector_divider_width_mm/2
        $corners = [System.Drawing.PointF[]]@(
            [System.Drawing.PointF]::new(($x1+$halfWidth*$vx),($y1+$halfWidth*$vy)),
            [System.Drawing.PointF]::new(($x2+$halfWidth*$vx),($y2+$halfWidth*$vy)),
            [System.Drawing.PointF]::new(($x2-$halfWidth*$vx),($y2-$halfWidth*$vy)),
            [System.Drawing.PointF]::new(($x1-$halfWidth*$vx),($y1-$halfWidth*$vy)))
        $dividerPath = [System.Drawing.Drawing2D.GraphicsPath]::new()
        $dividerPath.AddPolygon($corners)
        $dividers.Add('<path d="'+(SvgPath $dividerPath)+'"/>')
        $graphics.FillPath([System.Drawing.Brushes]::Black,$dividerPath)
        $dividerPath.Dispose()
        }
    }
    $caption = OutlinedText $centerText ([double]$design.caption_height_mm) $cx $cy 0 0 $false
    $paths.Add('<path data-role="caption" d="'+(SvgPath $caption)+'"/>')
    $graphics.FillPath([System.Drawing.Brushes]::Black,$caption);$caption.Dispose()
    $graphics.DrawEllipse($cutPen,[single]($cx-$radius),[single]($cy-$radius),[single](2*$radius),[single](2*$radius))
    $svg = @"
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="21.5mm" height="21.5mm" viewBox="0 0 21.5 21.5">
<title>$name — 15.5 mm radial cardstock trial label</title>
<desc>Black outlined lettering and any sector dividers are engraving geometry; red circle is the perimeter cut path. Captions are centered; neither label has ticks. Only ASA has sector dividers, midway between adjacent values; exposure allows intermediate settings. Engrave first and cut last. Nominal circle diameter 15.5 mm, no center hole, no kerf compensation. Font outlines are portable and require no installed font. No laser power, speed, passes or machine commands are supplied. Physical knob rotation in the $($design.physical_increase_direction) direction selects increasing exposure time or ASA at a stationary body index. ASA 100-800 is a provisional gain convention, not calibrated sensitivity. Physical mounting and firmware calibration remain to test.</desc>
<g id="engrave-lettering" fill="#000000" fill-rule="evenodd" stroke="none">
$($paths -join "`n")
</g>
<g id="engrave-dividers" fill="#000000" stroke="none">
$($dividers -join "`n")
</g>
<g id="cut-perimeter" fill="none" stroke="#ff0000" stroke-width="0.05">
<circle cx="10.75" cy="10.75" r="$(Num $radius)"/>
</g>
</svg>
"@
    [System.IO.File]::WriteAllText((Join-Path $outDir ($basename+'.svg')),$svg,[System.Text.UTF8Encoding]::new($false))
    $bitmap.Save((Join-Path $outDir ($basename+'-preview.png')),[System.Drawing.Imaging.ImageFormat]::Png)
    $details | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $outDir ($basename+'-positions.json'))
    $cutPen.Dispose();$graphics.Dispose();$bitmap.Dispose()
}
try {
    DrawLabel 'Exposure' 'SEC' $design.exposure_markings $design.exposure_seconds 1.1 'exposure-15p5mm' $design.exposure_sector_dividers
    if ($null -ne $design.asa_markings) {
        DrawLabel 'ASA' 'ASA' $design.asa_markings $design.asa_values 1.35 'asa-15p5mm' $design.asa_sector_dividers
        # One importable sheet with the two discs and shared color operations.
        $pair = [System.Xml.XmlDocument]::new()
        $pair.LoadXml('<svg xmlns="http://www.w3.org/2000/svg" width="43mm" height="21.5mm" viewBox="0 0 43 21.5"><title>Exposure and provisional ASA — 15.5 mm cardstock trial labels</title><desc/></svg>')
        $pair.DocumentElement.SelectSingleNode('*[local-name()="desc"]').InnerText = (
            'Two 15.5 mm nominal cut circles, no center holes or kerf compensation. ' +
            'Exposure markings are reciprocal seconds: ' + ($design.exposure_markings -join ', ') + '. ' +
            'ASA markings: ' + ($design.asa_markings -join ', ') + ', corresponding provisionally to ' +
            ($design.asa_analog_gain_multipliers -join 'x, ') + 'x analog gain, not calibrated sensitivity. ' +
            'Both rotating labels select increasing values when turned ' + $design.physical_increase_direction +
            ' against a stationary body index. SEC and ASA captions are centered. No ticks; only ASA has sector dividers. ' +
            'Black filled outlines engrave first; red circles cut last. Import at 100% scale; overall canvas is 43 by 21.5 mm. ' +
            'No laser power, speed or machine commands are supplied.')
        $preview = [System.Drawing.Bitmap]::new(1720,860)
        $pg = [System.Drawing.Graphics]::FromImage($preview)
        $pg.Clear([System.Drawing.Color]::White)
        $names = @('exposure-15p5mm','asa-15p5mm')
        for ($k=0; $k -lt $names.Count; $k++) {
            $single = [System.Xml.XmlDocument]::new()
            $single.Load((Join-Path $outDir ($names[$k]+'.svg')))
            $wrapper = $pair.CreateElement('g','http://www.w3.org/2000/svg')
            $wrapper.SetAttribute('id',$names[$k])
            $wrapper.SetAttribute('transform',('translate('+(Num ($k*21.5))+',0)'))
            foreach ($child in $single.DocumentElement.ChildNodes) {
                if ($child.LocalName -ne 'g') { continue }
                $copy = $pair.ImportNode($child,$true)
                $copy.SetAttribute('id',($names[$k]+'-'+$copy.GetAttribute('id')))
                $wrapper.AppendChild($copy) | Out-Null
            }
            $pair.DocumentElement.AppendChild($wrapper) | Out-Null
            $partImage = [System.Drawing.Image]::FromFile((Join-Path $outDir ($names[$k]+'-preview.png')))
            $pg.DrawImageUnscaled($partImage,($k*860),0)
            $partImage.Dispose()
        }
        [System.IO.File]::WriteAllText((Join-Path $outDir 'knob-labels-15p5mm.svg'),$pair.OuterXml,[System.Text.UTF8Encoding]::new($false))
        $preview.Save((Join-Path $outDir 'knob-labels-15p5mm-preview.png'),[System.Drawing.Imaging.ImageFormat]::Png)
        $pg.Dispose();$preview.Dispose()
    }
} finally { $fontFamily.Dispose() }
