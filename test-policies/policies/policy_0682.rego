package compliance.validation.policy.allow.helpers.policy_0682

# Auto-generated policy 682 (Rego v1 syntax)
# Package: compliance.validation.policy.allow.helpers

# Metadata
metadata := {
    "policy_id": "0682",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0682_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0682_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0682_allowed if {
    input.user.active
    input.resource.public
}
