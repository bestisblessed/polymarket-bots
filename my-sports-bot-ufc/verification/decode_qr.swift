import Foundation
import Vision

for path in CommandLine.arguments.dropFirst() {
    let request = VNDetectBarcodesRequest()
    request.symbologies = [.qr]
    let handler = VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:])
    do {
        try handler.perform([request])
        let payloads = (request.results ?? []).compactMap { $0.payloadStringValue }
        let output: [String: Any] = ["image": path, "qr_payloads": payloads]
        let data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
        print(String(data: data, encoding: .utf8)!)
        if payloads.count != 1 { exit(1) }
    } catch {
        fputs("QR decoding failed: \(error)\n", stderr)
        exit(1)
    }
}
