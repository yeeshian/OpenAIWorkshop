## Frontend with React

The common backend application runs the agent selected in the .env file and connects to the frontend UI.

#### Prerequisites for React Frontend:

**Install Node.js (if not already installed):**

The React frontend requires Node.js 16+ and npm. Check if you have them installed:

```bash
node --version  # Should be v16 or higher
npm --version   # Should be v8 or higher
```

If not installed, download and install from:
- **Windows/macOS/Linux:** [https://nodejs.org/](https://nodejs.org/) (Download the LTS version)
- **Alternative (Windows):** Use `winget install OpenJS.NodeJS.LTS`
- **Alternative (macOS):** Use `brew install node`

#### Running with React:
**Configuration (Optional):**

The React frontend connects to `http://localhost:7000` by default. To customize the backend URL, create a `.env` file in the `react-frontend` directory:

```bash
# react-frontend/.env
REACT_APP_BACKEND_URL=http://localhost:7000
```

**Terminal 3 - Start React Frontend:**

```bash
# Navigate to the React frontend directory from agentic_ai/applications
cd react-frontend

# Install dependencies (first time only, or after package.json changes)
npm install

# Start the development server
npm start

# The React app will automatically open at http://localhost:3000
# If it doesn't open automatically, navigate to http://localhost:3000 in your browser
```
**Note**: The React app connects to the backend at `http://localhost:7000` by default. Make sure the backend is running before starting the React app.

**Troubleshooting:**

- **Port 3000 already in use?** The React app will prompt you to use a different port. Type `Y` to accept.
- **npm install fails?** Try clearing npm cache: `npm cache clean --force` and retry.
- **WebSocket connection errors?** Ensure the backend is running on port 7000 and firewall isn't blocking connections.

**Best for:** Agent Framework single-agent, magentic_group multi-agent, viewing internal agent processes


---
If you successfully completed all the steps, setup is complete and your agent should be running now!

Read more about [how it works →](04_how_it_works.md)


  

