import { z } from "zod";
export class SegerToolsController {
    server;
    segerService;
    constructor(server, segerService) {
        this.server = server;
        this.segerService = segerService;
        this.registerTools();
    }
    registerTools() {
        this.registerBaixarFaturasTool();
        this.registerDadosFaturaTool();
    }
    registerBaixarFaturasTool() {
        this.server.tool("baixar-faturas", "Baixa as faturas de uma ou mais instalações e retorna os PDFs", {
            codInstalacoes: z.array(z.string())
                .describe("Lista de códigos de instalação (ex: ['0160011111','0160022222'])"),
            dataIni: z.string()
                .describe("MÊS-ANO início (ex: 'JAN-2025')"),
            dataFim: z.string()
                .describe("MÊS-ANO fim (ex: 'MAR-2025')"),
        }, async ({ codInstalacoes, dataIni, dataFim }) => {
            const files = await this.segerService.getFaturas(codInstalacoes, dataIni, dataFim);
            return {
                content: files.map(({ name, content }) => ({
                    type: "resource",
                    resource: {
                        uri: name, // nome do arquivo
                        blob: content.toString("base64"), // base64 do PDF
                        mimeType: "application/pdf",
                    },
                })),
            };
        });
    }
    registerDadosFaturaTool() {
        this.server.tool("dados-fatura", "Retorna todos os dados de energia de uma fatura em JSON", {
            pdfPath: z.string()
                .describe("Caminho local para o arquivo PDF da fatura no servidor"),
        }, async ({ pdfPath }) => {
            const dados = await this.segerService.getDadosFatura(pdfPath);
            return {
                content: [
                    {
                        type: "text",
                        text: JSON.stringify(dados), // retorna o objeto JSON como string
                    },
                ],
            };
        });
    }
}
