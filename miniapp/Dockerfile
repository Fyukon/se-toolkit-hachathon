FROM node:22-alpine

WORKDIR /app

COPY package.json .
RUN npm install

COPY src ./src
COPY index.html .

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
