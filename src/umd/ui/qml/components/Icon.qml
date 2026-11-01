import QtQuick

Canvas {
    id: canvas
    property string name: "home"
    property color strokeColor: ink.muted
    implicitWidth: 16
    implicitHeight: 16
    antialiasing: true

    onNameChanged: requestPaint()
    onStrokeColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        ctx.strokeStyle = strokeColor
        ctx.fillStyle = strokeColor
        ctx.lineWidth = 1.6
        ctx.lineCap = "round"
        ctx.lineJoin = "round"
        var s = width / 16
        ctx.scale(s, s)
        ctx.beginPath()
        if (name === "back") {
            ctx.moveTo(10, 3); ctx.lineTo(5, 8); ctx.lineTo(10, 13)
        } else if (name === "forward") {
            ctx.moveTo(6, 3); ctx.lineTo(11, 8); ctx.lineTo(6, 13)
        } else if (name === "sidebar") {
            ctx.rect(1.5, 2.5, 13, 11)
            ctx.moveTo(6, 2.5); ctx.lineTo(6, 13.5)
        } else if (name === "home") {
            ctx.moveTo(2, 7); ctx.lineTo(8, 2.5); ctx.lineTo(14, 7)
            ctx.lineTo(14, 13.5); ctx.lineTo(2, 13.5); ctx.closePath()
        } else if (name === "download") {
            ctx.moveTo(8, 2); ctx.lineTo(8, 10)
            ctx.moveTo(5, 7.5); ctx.lineTo(8, 10.5); ctx.lineTo(11, 7.5)
            ctx.moveTo(3, 13); ctx.lineTo(13, 13)
        } else if (name === "clock") {
            ctx.arc(8, 8, 5.5, 0, Math.PI * 2)
            ctx.moveTo(8, 5); ctx.lineTo(8, 8); ctx.lineTo(10.5, 9.5)
        } else if (name === "folder") {
            ctx.moveTo(1.5, 4); ctx.lineTo(6, 4); ctx.lineTo(7.5, 6)
            ctx.lineTo(14.5, 6); ctx.lineTo(14.5, 13); ctx.lineTo(1.5, 13); ctx.closePath()
        } else if (name === "video") {
            ctx.rect(1.5, 3.5, 13, 9)
            ctx.moveTo(6.5, 6); ctx.lineTo(10.5, 8); ctx.lineTo(6.5, 10); ctx.closePath()
        } else if (name === "settings") {
            ctx.arc(8, 8, 2.2, 0, Math.PI * 2)
            ctx.moveTo(8, 1.5); ctx.lineTo(8, 3.2)
            ctx.moveTo(8, 12.8); ctx.lineTo(8, 14.5)
            ctx.moveTo(1.5, 8); ctx.lineTo(3.2, 8)
            ctx.moveTo(12.8, 8); ctx.lineTo(14.5, 8)
        } else if (name === "link") {
            ctx.moveTo(6.5, 9.5); ctx.lineTo(9.5, 6.5)
            ctx.moveTo(5, 7); ctx.bezierCurveTo(3, 5, 3, 3, 6, 3)
            ctx.moveTo(11, 9); ctx.bezierCurveTo(13, 11, 13, 13, 10, 13)
        } else if (name === "info") {
            ctx.arc(8, 8, 6, 0, Math.PI * 2)
            ctx.moveTo(8, 7); ctx.lineTo(8, 11.5)
            ctx.moveTo(8, 4.6); ctx.lineTo(8, 4.8)
        } else if (name === "grid") {
            ctx.rect(2, 2, 5, 5)
            ctx.rect(9, 2, 5, 5)
            ctx.rect(2, 9, 5, 5)
            ctx.rect(9, 9, 5, 5)
        } else if (name === "image") {
            ctx.rect(1.5, 2.5, 13, 11)
            ctx.moveTo(3, 11); ctx.lineTo(6.5, 7.5); ctx.lineTo(9, 10); ctx.lineTo(13, 6)
        }
        ctx.stroke()
    }
}
