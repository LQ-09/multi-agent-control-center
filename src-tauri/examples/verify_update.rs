//! Release check: cargo run --example verify_update -- CONFIG MANIFEST ARCHIVE
use base64::{Engine, engine::general_purpose::STANDARD};
use minisign_verify::{PublicKey, Signature};
fn main() {
    let args:Vec<String>=std::env::args().collect();
    assert_eq!(args.len(),4,"Expected config, manifest and archive paths");
    let config:serde_json::Value=serde_json::from_slice(&std::fs::read(&args[1]).unwrap()).unwrap();
    let manifest:serde_json::Value=serde_json::from_slice(&std::fs::read(&args[2]).unwrap()).unwrap();
    let decode=|s:&str|String::from_utf8(STANDARD.decode(s).unwrap()).unwrap();
    let public=PublicKey::decode(&decode(config["plugins"]["updater"]["pubkey"].as_str().unwrap())).unwrap();
    let text=decode(manifest["platforms"]["darwin-aarch64"]["signature"].as_str().unwrap());
    let signature=Signature::decode(&text).unwrap();
    let mut bytes=std::fs::read(&args[3]).unwrap();
    public.verify(&bytes,&signature,false).unwrap();
    let version=manifest["version"].as_str().unwrap();
    assert_eq!(config["version"].as_str().unwrap(),version);
    assert!(text.lines().any(|l|l.starts_with("trusted comment:")&&l.split('\t').any(|v|v==format!("app-version:{version}"))));
    bytes[0]^=1;
    assert!(public.verify(&bytes,&signature,false).is_err(),"Tampered artifact was accepted");
    println!("PASS: release signature, signed version, and tamper rejection");
}
