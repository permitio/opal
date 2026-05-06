package security.validation.resource.deny.policy_0873

# Auto-generated policy 873 (Rego v1 syntax)
# Package: security.validation.resource.deny

# Metadata
metadata := {
    "policy_id": "0873",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0873_allowed if {
    input.user.role == "admin"
}
default policy_0873_allowed = false
policy_0873_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
