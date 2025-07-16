permit(
    principal in Role::"Editor",
    action in [
        Action::"document:read",
        Action::"document:write",
        Action::"document:delete"
	],
    resource in ResourceType::"document"
);
