package risk.authentication.resource.allow.policy_0249

# Auto-generated policy 249 (Rego v1 syntax)
# Package: risk.authentication.resource.allow

# Metadata
metadata := {
    "policy_id": "0249",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0249_allowed if {
    input.user.active
    input.resource.public
}
policy_0249_allowed if {
    input.user.role == "admin"
}
