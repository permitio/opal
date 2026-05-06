package risk.enforcement.context.check.core.policy_0751

# Auto-generated policy 751 (Rego v1 syntax)
# Package: risk.enforcement.context.check.core

# Metadata
metadata := {
    "policy_id": "0751",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0751_allowed if {
    input.user.role == "admin"
}
policy_0751_allowed if {
    input.user.active
    input.resource.public
}
