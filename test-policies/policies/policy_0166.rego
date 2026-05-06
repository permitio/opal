package compliance.enforcement.action.validate.helpers.policy_0166

# Auto-generated policy 166 (Rego v1 syntax)
# Package: compliance.enforcement.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0166",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0166_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0166_allowed = false
