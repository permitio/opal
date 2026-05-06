package security.monitoring.policy.verify.policy_0726

# Auto-generated policy 726 (Rego v1 syntax)
# Package: security.monitoring.policy.verify

# Metadata
metadata := {
    "policy_id": "0726",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0726_allowed = false
policy_0726_allowed if {
    input.user.role == "admin"
}
policy_0726_allowed if {
    input.user.active
    input.resource.public
}
policy_0726_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
