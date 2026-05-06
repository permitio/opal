package compliance.authorization.action.allow.policy_0201

# Auto-generated policy 201 (Rego v1 syntax)
# Package: compliance.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0201",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0201_allowed if {
    input.user.role == "admin"
}
policy_0201_allowed if {
    input.user.active
    input.resource.public
}
