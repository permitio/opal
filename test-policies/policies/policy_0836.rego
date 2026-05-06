package security.monitoring.resource.deny.policy_0836

# Auto-generated policy 836 (Rego v1 syntax)
# Package: security.monitoring.resource.deny

# Metadata
metadata := {
    "policy_id": "0836",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0836_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0836_allowed if {
    input.user.active
    input.resource.public
}
policy_0836_allowed if {
    input.user.role == "admin"
}
