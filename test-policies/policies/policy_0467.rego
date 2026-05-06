package security.monitoring.resource.verify.policy_0467

# Auto-generated policy 467 (Rego v1 syntax)
# Package: security.monitoring.resource.verify

# Metadata
metadata := {
    "policy_id": "0467",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0467_allowed if {
    input.user.active
    input.resource.public
}
policy_0467_allowed if {
    data.policies.security.enabled
}
policy_0467_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0467_allowed if {
    input.user.role == "admin"
}
