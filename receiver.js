const express = require('express');

const app = express();
app.use(express.json());

// temp database
const recipesDb = {};

app.post('/submit_recipe', (req, res) => {
    const recipe = req.body;
    
    if (!recipe.title || !recipe.ingredients || !recipe.instructions || !recipe.author) {
        return res.status(400).json({ error: "Missing required recipe fields" });
    }

    if (recipe.author in recipesDb) {
        recipesDb[recipe.author].push(recipe);
    } else {
        recipesDb[recipe.author] = [recipe];
    }

    return res.json({
        message: `Recipe "${recipe.title}" saved successfully for ${recipe.author}!`
    });
});

app.get('/get_recipes/:author', (req, res) => {
    const { author } = req.params;
    
    if (author in recipesDb) {
        return res.json({ author, recipes: recipesDb[author] });
    }
    return res.status(404).json({ message: `No recipes found for ${author} `});
});

app.get('/all_recipes', (_req, res) => {
    return res.json(recipesDb);
});

const PORT = 5002;
app.listen(PORT, '0.0.0.0', () => {
    console.log(`Recipe receiver service running on port ${PORT}`);
});