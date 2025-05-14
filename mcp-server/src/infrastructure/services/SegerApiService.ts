
import fs from "fs/promises";
import path from "path";

interface SegerFaturasResponse {
  message: string;
  pdfs: string[]; // caminhos no disco retornados pelo Flask
}

export interface FaturaFile {
  name: string;
  content: Buffer;
}

export interface ConsumoResult {
  consumoPonta: number;
  consumoForaPonta: number;
  // … outros campos que você extrai do JSON
}

export interface DadosFatura {
  leituraInicio: string;
  leituraFim: string;
  consumoPonta: number;
  consumoForaPonta: number;
  demandaContratada?: number;
  valorTotal: number;
  tarifas: Array<{ periodo: string; valor: number }>;
  impostos: Array<{ nome: string; valor: number }>;
  // … adicione aqui todos os campos retornados pelo Flask
}

export class SegerApiService{

     constructor() {}

    private readonly API_BASE="http://localhost:5000/api/seger";
    private readonly USER_AGENT = "seger-app/1.0";
    protected readonly DEFAULT_HEADERS = {
        "Content-Type": "application/json",
    };

    // Helper function for making Seger API requests
    async makeRequest<T>(
        endpoint: string, 
        method: "GET" | "POST" | "PUT" | "DELETE" = "GET",
        body?: object
    ): Promise<T | null> {
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
        return resp.json() as Promise<T>;
    }

   /**
   * Baixa metadados da fatura e depois lê os arquivos do disco,
   * retornando o conteúdo binário em memória.
   */
    async getFaturas(
        codInstalacoes: string[],
        dataIni: string,
        dataFim: string
    ): Promise<FaturaFile[]> {
        // 1) pega os paths dos PDFs no servidor Flask
        const resp = await this.makeRequest<SegerFaturasResponse>(
        "/faturas",
        "POST",
        { codInstalacoes, data_inicio: dataIni, data_fim: dataFim }
        );

        if(!resp){
            throw new Error(`Erro ao obter arquivos pdfs`);
        }
        // 2) para cada path, lê o arquivo e empacota em Buffer
        const files = await Promise.all(
            resp.pdfs.map(async (pdfPath) => ({
            name: path.basename(pdfPath),
            content: await fs.readFile(pdfPath),
            }))
        );
        return files;
    }

    /**
   * POST /dados-fatura
   * Recebe pdf_path e retorna TODOS os dados de energia da fatura em JSON.
   */
    async getDadosFatura(pdfPath: string): Promise<DadosFatura> {
        const result = await this.makeRequest<DadosFatura>(
        "/dados-fatura",
        "POST",
        { pdf_path: pdfPath }
        );
        if (!result) {
            throw new Error(`Não foi possível obter dados da fatura em ${pdfPath}`);
        }
        return result;
    }
    
}