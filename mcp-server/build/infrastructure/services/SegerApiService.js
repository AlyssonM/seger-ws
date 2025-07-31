import fs from "fs/promises";
import path from "path";
export class SegerApiService {
    constructor() { }
    API_BASE = "https://5001-firebase-studio-1749560787008.cluster-vpxjqdstfzgs6qeiaf7rdlsqrc.cloudworkstations.dev/api/seger";
    USER_AGENT = "seger-app/1.0";
    DEFAULT_HEADERS = {
        "Content-Type": "application/json",
    };
    // Helper function for making Seger API requests
    async makeRequest(endpoint, method = "GET", body) {
        const url = `${this.API_BASE}${endpoint}`;
        const resp = await fetch(url, {
            method,
            headers: this.DEFAULT_HEADERS,
            body: body ? JSON.stringify(body) : undefined,
        });
        if (!resp.ok) {
            const text = await resp.text();
            console.error(`[${method}] ${url} → ${resp.status}`, text);
            throw new Error(`HTTP ${resp.status} @ ${url}`);
        }
        return resp.json();
    }
    /**
    * Baixa metadados da fatura e depois lê os arquivos do disco,
    * retornando o conteúdo binário em memória.
    */
    async getFaturas(codInstalacoes, dataIni, dataFim) {
        // 1) pega os paths dos PDFs no servidor Flask
        const resp = await this.makeRequest("/faturas", "POST", { codInstalacoes, data_inicio: dataIni, data_fim: dataFim });
        if (!resp) {
            throw new Error(`Erro ao obter arquivos pdfs`);
        }
        // 2) para cada path, lê o arquivo e empacota em Buffer
        const files = await Promise.all(resp.pdfs.map(async (pdfPath) => ({
            name: path.basename(pdfPath),
            content: await fs.readFile(pdfPath),
        })));
        return files;
    }
    /**
   * POST /dados-fatura
   * Recebe pdf_path e retorna TODOS os dados de energia da fatura em JSON.
   */
    async getDadosFatura(pdfPath) {
        const result = await this.makeRequest("/dados-fatura", "POST", { pdf_path: pdfPath });
        if (!result) {
            throw new Error(`Não foi possível obter dados da fatura em ${pdfPath}`);
        }
        return result;
    }
    /**
     * POST /analisar-fatura
     * Realiza análise completa de faturas energéticas
     */
    async analisarFaturas(request) {
        const result = await this.makeRequest("/analisar-fatura", "POST", request);
        if (!result) {
            throw new Error(`Não foi possível realizar análise para instalação ${request.codInstalacao}`);
        }
        return result;
    }
}
