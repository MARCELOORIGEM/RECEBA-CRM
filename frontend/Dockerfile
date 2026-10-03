# Painel do Miliano CRM: compila com Node e serve com Nginx.
FROM node:20-alpine AS build

WORKDIR /app

# O endereço da API entra no bundle em tempo de build — Create React App
# substitui as variáveis na compilação, não na execução.
ARG REACT_APP_BACKEND_URL=""
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
# As credenciais de demonstração nunca aparecem em imagem de produção.
ENV REACT_APP_SHOW_DEMO_LOGIN=false

COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile --network-timeout 600000

COPY . .
RUN yarn build

# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine

COPY --from=build /app/build /usr/share/nginx/html
# O arquivo vive aqui, e não em infra/, porque o contexto do build é esta pasta
# — `COPY ../algo` não alcança nada fora dela.
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
