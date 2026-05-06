package governance.validation.policy.deny.policy_0765

# Auto-generated policy 765 (Rego v1 syntax)
# Package: governance.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0765",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0765_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0765_allowed if {
    input.user.active
    input.resource.public
}
