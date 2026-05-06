package compliance.validation.resource.deny.helpers.policy_0038

# Auto-generated policy 38 (Rego v1 syntax)
# Package: compliance.validation.resource.deny.helpers

# Metadata
metadata := {
    "policy_id": "0038",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0038_allowed if {
    input.user.role == "admin"
}
policy_0038_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0038_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
