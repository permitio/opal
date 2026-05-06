package compliance.authentication.policy.allow.helpers.policy_0309

# Auto-generated policy 309 (Rego v1 syntax)
# Package: compliance.authentication.policy.allow.helpers

# Metadata
metadata := {
    "policy_id": "0309",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0309_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0309_allowed if {
    input.user.role == "admin"
}
policy_0309_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
