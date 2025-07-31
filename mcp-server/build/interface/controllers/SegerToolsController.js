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
        this.registerDadosConsolidadosTool();
        this.registerStartAnalysisTool();
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
    registerDadosConsolidadosTool() {
        this.server.tool("dados-consolidados", "Obtém dados consolidados de faturas de uma instalação para um período específico", {
            codInstalacao: z.string()
                .describe("Código da instalação (ex: '0000144112')"),
            data_inicio: z.string()
                .describe("Data início no formato MES-ANO (ex: 'JAN-2025')"),
            data_fim: z.string()
                .describe("Data fim no formato MES-ANO (ex: 'ABR-2025')"),
            distribuidora: z.string().optional()
                .describe("Distribuidora (padrão: 'EDP ES')"),
        }, async ({ codInstalacao, data_inicio, data_fim, distribuidora = "EDP ES" }) => {
            try {
                console.error(`[MCP] Obtendo dados consolidados para instalação: ${codInstalacao}`);
                console.error(`[MCP] Período: ${data_inicio} até ${data_fim}`);
                console.error(`[MCP] Distribuidora: ${distribuidora}`);
                const dados = await this.segerService.getFaturasJson({
                    codInstalacao,
                    data_inicio,
                    data_fim,
                    distribuidora,
                    via_regex: true
                });
                console.error(`[MCP] Dados consolidados obtidos com sucesso - ${dados.total_faturas} faturas`);
                return {
                    content: [
                        {
                            type: "text",
                            text: `Dados consolidados da instalação ${codInstalacao} (${data_inicio} a ${data_fim}):\n\n` +
                                `Total de faturas: ${dados.total_faturas}\n` +
                                `Distribuidora: ${distribuidora}\n\n` +
                                `Dados detalhados:\n${JSON.stringify(dados, null, 2)}`
                        }
                    ]
                };
            }
            catch (error) {
                console.error(`[MCP] Erro ao obter dados consolidados:`, error);
                return {
                    content: [
                        {
                            type: "text",
                            text: `Erro ao obter dados consolidados da instalação ${codInstalacao}:\n` +
                                `${error instanceof Error ? error.message : 'Erro desconhecido'}\n\n` +
                                `Verifique se:\n` +
                                `- A instalação existe: ${codInstalacao}\n` +
                                `- O período é válido: ${data_inicio} a ${data_fim}\n` +
                                `- Existem faturas para o período solicitado\n` +
                                `- O backend está respondendo corretamente`
                        }
                    ]
                };
            }
        });
    }
    registerStartAnalysisTool() {
        this.server.tool("seger-tools/start_analysis", "Inicia análise energética completa para instalações usando credenciais padrão", {
            installations: z.array(z.string())
                .describe("Lista de códigos de instalação (ex: ['0000144112'])"),
            start_date: z.string()
                .describe("Data início no formato MM/YYYY (ex: '05/2024')"),
            end_date: z.string()
                .describe("Data fim no formato MM/YYYY (ex: '04/2025')"),
        }, async ({ installations, start_date, end_date }) => {
            // Usar credenciais padrão
            const defaultUser = "lohanebpalaoro@gmail.com";
            const defaultPassword = "Lohane@29";
            // Converter formato de data MM/YYYY para MMM-YYYY
            const convertDateFormat = (date) => {
                const [month, year] = date.split('/');
                const monthNames = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN',
                    'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'];
                const monthIndex = parseInt(month) - 1;
                return `${monthNames[monthIndex]}-${year}`;
            };
            try {
                console.error(`[MCP] Iniciando análise para: ${installations.join(', ')}`);
                console.error(`[MCP] Período: ${start_date} até ${end_date}`);
                console.error(`[MCP] Usuário: ${defaultUser}`);
                const convertedStartDate = convertDateFormat(start_date);
                const convertedEndDate = convertDateFormat(end_date);
                console.error(`[MCP] Datas convertidas: ${convertedStartDate} até ${convertedEndDate}`);
                const analysisResult = await this.segerService.analisarFaturas({
                    codInstalacao: installations[0], // Por enquanto, usar primeira instalação
                    data_inicio: convertedStartDate,
                    data_fim: convertedEndDate,
                    periodo: convertedEndDate, // Usar data fim como período de referência
                    distribuidora: "CPFL", // Distribuidora padrão
                    username: defaultUser,
                    password: defaultPassword
                });
                console.error(`[MCP] Análise concluída com sucesso`);
                return {
                    content: [
                        {
                            type: "text",
                            text: `Análise da instalação ${installations[0]} concluída com sucesso!\n\n` +
                                `Período analisado: ${start_date} a ${end_date}\n` +
                                `Usuário: ${defaultUser}\n\n` +
                                `Resultados:\n${JSON.stringify(analysisResult, null, 2)}`
                        }
                    ]
                };
            }
            catch (error) {
                console.error(`[MCP] Erro na análise:`, error);
                return {
                    content: [
                        {
                            type: "text",
                            text: `Erro ao realizar análise da instalação ${installations[0]}:\n` +
                                `${error instanceof Error ? error.message : 'Erro desconhecido'}\n\n` +
                                `Verifique se:\n` +
                                `- A instalação existe: ${installations[0]}\n` +
                                `- O período é válido: ${start_date} a ${end_date}\n` +
                                `- O backend está respondendo corretamente`
                        }
                    ]
                };
            }
        });
    }
}
