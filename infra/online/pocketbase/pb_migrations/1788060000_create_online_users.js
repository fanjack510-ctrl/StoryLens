migrate((app) => {
  try {
    app.findCollectionByNameOrId("users")
    return
  } catch {
    // The collection is absent and will be created below.
  }

  const collection = new Collection({
    type: "auth",
    name: "users",
    listRule: "id = @request.auth.id",
    viewRule: "id = @request.auth.id",
    createRule: "",
    updateRule: "id = @request.auth.id",
    deleteRule: "id = @request.auth.id",
    manageRule: null,
    fields: [],
    passwordAuth: {
      enabled: true,
      identityFields: ["email"],
    },
  })

  app.save(collection)
})
