const express = require('express');
const axios = require('axios');

const app = express();
app.use(express.json());

const RECIPE_SERVICE_URL = "http://192.168.64.4:5002";

app.post('/submit_recipe', async (req, res) => {
    const recipe = req.body;

    if (!recipe.title || !recipe.ingredients || !recipe.instructions || !recipe.author) {
        return res.status(400).json({ error: "Missing required recipe fields" });
    }

    try {
        const response = await axios.post(`${RECIPE_SERVICE_URL}/receive_recipe, recipe`);
        return res.status(response.status).json(response.data);
    } catch (error) {
        return res.status(500).json({ error: "Failed to submit recipe" });
    }
});

app.get('/get_recipes/:author', async (req, res) => {
    const { author } = req.params;
    
    try {
        const response = await axios.get(`${RECIPE_SERVICE_URL}/get_recipes/${author}`);
        return res.status(response.status).json(response.data);
    } catch (error) {
        return res.status(500).json({ error: "Failed to fetch recipes" });
    }
});

const PORT = 5001;
app.listen(PORT, '0.0.0.0', () => {
    console.log(`Recipe sender service running on port ${PORT}`);
});