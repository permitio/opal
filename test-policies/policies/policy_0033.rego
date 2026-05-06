package audit.monitoring.policy.check.policy_0033

# Auto-generated policy 33 (Rego v1 syntax)
# Package: audit.monitoring.policy.check

# Metadata
metadata := {
    "policy_id": "0033",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0033_allowed if {
    input.user.active
    input.resource.public
}
policy_0033_allowed if {
    input.user.role == "admin"
}
policy_0033_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
