import Foundation
import AVFoundation
import CoreImage
let path = CommandLine.arguments[1], secs = Double(CommandLine.arguments[2])!, out = CommandLine.arguments[3]
let asset = AVURLAsset(url: URL(fileURLWithPath: path))
let gen = AVAssetImageGenerator(asset: asset)
gen.requestedTimeToleranceBefore = .zero; gen.requestedTimeToleranceAfter = .zero
gen.appliesPreferredTrackTransform = true
do {
    let cg = try gen.copyCGImage(at: CMTime(seconds: secs, preferredTimescale: 600), actualTime: nil)
    let ci = CIImage(cgImage: cg)
    try CIContext().writePNGRepresentation(of: ci, to: URL(fileURLWithPath: out), format: .RGBA8, colorSpace: CGColorSpaceCreateDeviceRGB())
    print("wrote \(out)  \(cg.width)x\(cg.height)")
} catch { print("ERROR \(error)") }
