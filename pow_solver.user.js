// ==UserScript==
// @name         Erebos PoW Solver
// @namespace    http://erebos.network/
// @version      1.0
// @description  Löst automatisch den Proof-of-Work für das Erebos Netzwerk
// @match        *://*.erebos/*
// @grant        none
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    // Wir prüfen, ob die aktuelle Seite eine 429-Antwort ist (PoW required)
    // Da der Browser bei einem 429 normalerweise den Body anzeigt, 
    // injizieren wir unseren Code, um den PoW zu lösen.
    
    // Hinweis: In einem echten Browser-Add-on (z.B. Firefox WebExtension) 
    // könnte man die Header direkt via webRequest API auslesen.
    // Hier nutzen wir einen Workaround: Wir triggern einen Fetch und lesen die Header.
    
    async function solvePow() {
        try {
            // Wir machen einen HEAD-Request an die aktuelle URL, um die Header zu bekommen
            const url = window.location.href;
            const response = await fetch(url, { method: 'HEAD' });
            
            if (response.status === 429) {
                const nonce = response.headers.get('X-Erebos-PoW-Nonce');
                const difficulty = parseInt(response.headers.get('X-Erebos-PoW-Difficulty') || '4', 10);
                
                if (!nonce) return;
                
                console.log(`[Erebos PoW] Challenge empfangen: nonce=${nonce}, difficulty=${difficulty}`);
                
                // PoW lösen: Wir suchen eine Zahl, sodass sha256(nonce + zahl) mit `difficulty` Nullen beginnt
                let solution = 0;
                const target = '0'.repeat(difficulty);
                
                // Web Crypto API nutzen für performantes Hashing
                async function sha256Hex(msg) {
                    const msgBuffer = new TextEncoder().encode(msg);
                    const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
                    const hashArray = Array.from(new Uint8Array(hashBuffer));
                    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
                }
                
                console.log(`[Erebos PoW] Beginne Berechnung...`);
                
                while (true) {
                    const hash = await sha256Hex(nonce + solution.toString());
                    if (hash.startsWith(target)) {
                        console.log(`[Erebos PoW] Lösung gefunden: ${solution} (Hash: ${hash.substring(0, 10)}...)`);
                        break;
                    }
                    solution++;
                    
                    // Alle 10.000 Versuche ein Yield, damit der Browser nicht einfriert
                    if (solution % 10000 === 0) {
                        await new Promise(r => setTimeout(r, 0));
                    }
                }
                
                // Jetzt müssen wir den Request mit der Lösung wiederholen.
                // Da wir keine Custom-Header bei einer normalen Navigation setzen können,
                // nutzen wir einen Trick: Wir hängen die Lösung als Query-Parameter an
                // und leiten den Browser weiter. Der Server muss diese Parameter akzeptieren.
                // (Das erfordert einen kleinen Patch am Server).
                
                const newUrl = new URL(url);
                newUrl.searchParams.set('pow_nonce', nonce);
                newUrl.searchParams.set('pow_solution', solution.toString());
                
                console.log(`[Erebos PoW] Leite weiter zu: ${newUrl.toString()}`);
                window.location.replace(newUrl.toString());
            }
        } catch (e) {
            console.error("[Erebos PoW] Fehler:", e);
        }
    }

    // Wenn die Seite geladen ist und den 429-Text anzeigt, starten wir den Solver
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', solvePow);
    } else {
        solvePow();
    }
})();
