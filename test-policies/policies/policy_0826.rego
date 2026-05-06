package compliance.validation.resource.deny.policy_0826

# Auto-generated policy 826 (Rego v1 syntax)
# Package: compliance.validation.resource.deny

# Metadata
metadata := {
    "policy_id": "0826",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0826_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0826_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0826_allowed if {
    input.user.role == "admin"
}
