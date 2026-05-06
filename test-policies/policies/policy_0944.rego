package audit.validation.resource.deny.helpers.policy_0944

# Auto-generated policy 944 (Rego v1 syntax)
# Package: audit.validation.resource.deny.helpers

# Metadata
metadata := {
    "policy_id": "0944",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0944_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0944_allowed if {
    input.user.role == "admin"
}
